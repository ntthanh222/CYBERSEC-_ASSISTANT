"""Byte-level upload MIME sniffing, exercised through the real upload API.

Codex blocked Phase 2.6 (source ``649c6f4``) because ``detect_kind`` trusted
the client-declared ``Content-Type``/filename extension instead of the
actual file bytes. These tests drive the real
``POST /api/knowledge/documents`` path (not just the ``detect_kind`` unit
helper in test_knowledge_extraction.py) to prove the fix end to end: a
mismatch between declared type and real content is now a hard 415, and a
file that byte-sniffs as unrecognizable is rejected outright - see
docs/RAG_SECURITY.md for the full policy table this suite verifies.
"""
import io

import pytest
from pypdf import PdfWriter
from reportlab.pdfgen import canvas

from ._knowledge_fakes import FakeEmbeddingProvider


@pytest.fixture(autouse=True)
def _fast_embeddings(monkeypatch):
    monkeypatch.setattr(
        "backend.services.knowledge.get_embedding_provider", lambda: FakeEmbeddingProvider()
    )


def _build_pdf(pages: list[str] = ("Some real text content.",)) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(400, 400))
    for page_text in pages:
        pdf.drawString(50, 350, page_text)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _build_image_only_pdf() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(400, 400))
    pdf.showPage()  # blank page - no text layer, same shape as a scanned page
    pdf.save()
    return buffer.getvalue()


def _build_encrypted_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(user_password="secret", owner_password="secret2")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _upload(client, *, filename: str, content: bytes, content_type: str):
    files = {"file": (filename, io.BytesIO(content), content_type)}
    return client.post("/api/knowledge/documents", files=files)


# 1. Real PDF + .pdf + application/pdf -> PASS.
def test_real_pdf_matching_extension_and_content_type_is_accepted(api_client):
    response = _upload(
        api_client, filename="report.pdf", content=_build_pdf(), content_type="application/pdf"
    )
    assert response.status_code == 201
    assert response.json()["document"]["processing_status"] == "ready"


# 2. Real PDF but filename .txt -> FAIL mismatch.
def test_real_pdf_with_txt_extension_is_rejected(api_client):
    response = _upload(
        api_client, filename="report.txt", content=_build_pdf(), content_type="application/pdf"
    )
    assert response.status_code == 415


# 3. Real PDF but Content-Type text/plain -> FAIL.
def test_real_pdf_with_text_content_type_is_rejected(api_client):
    response = _upload(
        api_client, filename="report.pdf", content=_build_pdf(), content_type="text/plain"
    )
    assert response.status_code == 415


# 4. Plain text renamed to .pdf -> FAIL.
def test_plain_text_renamed_to_pdf_is_rejected(api_client):
    response = _upload(
        api_client,
        filename="fake.pdf",
        content=b"This is just plain text, not a PDF.",
        content_type="application/pdf",
    )
    assert response.status_code == 415


# 5. Binary file renamed to .txt -> FAIL.
def test_binary_file_renamed_to_txt_is_rejected(api_client):
    binary = bytes(range(256)) * 4
    response = _upload(api_client, filename="notes.txt", content=binary, content_type="text/plain")
    assert response.status_code == 415


# 6. EXE/ZIP/image renamed to .pdf -> FAIL.
def test_zip_renamed_to_pdf_is_rejected(api_client):
    zip_bytes = b"PK\x03\x04" + bytes(range(256)) * 4
    response = _upload(
        api_client, filename="malware.pdf", content=zip_bytes, content_type="application/pdf"
    )
    assert response.status_code == 415


def test_exe_renamed_to_pdf_is_rejected(api_client):
    exe_bytes = b"MZ" + bytes(range(256)) * 4
    response = _upload(
        api_client, filename="malware.pdf", content=exe_bytes, content_type="application/pdf"
    )
    assert response.status_code == 415


def test_png_renamed_to_pdf_is_rejected(api_client):
    png_bytes = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4
    response = _upload(
        api_client, filename="image.pdf", content=png_bytes, content_type="application/pdf"
    )
    assert response.status_code == 415


# 7. Valid UTF-8 TXT -> PASS.
def test_valid_utf8_txt_is_accepted(api_client):
    response = _upload(
        api_client,
        filename="notes.txt",
        content="Ghi chú vận hành an toàn.".encode("utf-8"),
        content_type="text/plain",
    )
    assert response.status_code == 201


# 8. UTF-8 BOM TXT -> PASS.
def test_utf8_bom_txt_is_accepted(api_client):
    content = b"\xef\xbb\xbf" + "Runbook with a BOM.".encode("utf-8")
    response = _upload(api_client, filename="notes.txt", content=content, content_type="text/plain")
    assert response.status_code == 201


# 9. Valid Vietnamese Markdown -> PASS.
def test_vietnamese_markdown_is_accepted(api_client):
    content = "# Ứng phó sự cố\n\nCách ly máy chủ bị nhiễm ngay lập tức.\n".encode("utf-8")
    response = _upload(
        api_client, filename="incident.md", content=content, content_type="text/markdown"
    )
    assert response.status_code == 201


# 10. Markdown with raw HTML/script -> ingested as untrusted text (backend
# never executes it; sanitized-on-render is enforced by the frontend, see
# frontend/src/tests/Phase2_6RAG.test.tsx and the citation renderer).
def test_markdown_with_raw_html_is_ingested_as_untrusted_text(api_client):
    content = "# Notes\n\n<script>alert('xss')</script>\n\nSafe text.".encode("utf-8")
    response = _upload(
        api_client, filename="notes.md", content=content, content_type="text/markdown"
    )
    assert response.status_code == 201
    assert response.json()["document"]["processing_status"] == "ready"


# 11. Text containing a NUL byte -> FAIL.
def test_text_with_nul_byte_is_rejected(api_client):
    content = b"Some text\x00with a NUL byte in the middle."
    response = _upload(api_client, filename="notes.txt", content=content, content_type="text/plain")
    assert response.status_code == 415


# 12. Invalid UTF-8 -> FAIL.
def test_invalid_utf8_is_rejected(api_client):
    content = b"\xff\xfe\x00bad-encoding"
    response = _upload(api_client, filename="notes.txt", content=content, content_type="text/plain")
    assert response.status_code == 415


# 13. Empty/whitespace-only file -> FAIL.
def test_whitespace_only_file_is_rejected(api_client):
    response = _upload(
        api_client, filename="notes.txt", content=b"   \n\t  \n", content_type="text/plain"
    )
    assert response.status_code == 400


def test_zero_byte_file_is_rejected(api_client):
    response = _upload(api_client, filename="notes.txt", content=b"", content_type="text/plain")
    assert response.status_code == 400


# 14. Generic application/octet-stream + real PDF bytes + .pdf extension ->
# accepted per the documented policy (bytes + extension agree; a generic
# declared type never blocks a valid detection).
def test_generic_content_type_with_pdf_bytes_and_pdf_extension_is_accepted(api_client):
    response = _upload(
        api_client,
        filename="report.pdf",
        content=_build_pdf(),
        content_type="application/octet-stream",
    )
    assert response.status_code == 201


# 15. Generic application/octet-stream + unknown binary -> FAIL.
def test_generic_content_type_with_unknown_binary_is_rejected(api_client):
    binary = bytes(range(256)) * 4
    response = _upload(
        api_client, filename="file.bin", content=binary, content_type="application/octet-stream"
    )
    assert response.status_code == 415


# 16. Malformed/truncated PDF -> FAIL safely (bytes sniff as PDF via the
# magic header, but the real parser rejects the corrupt structure).
def test_truncated_pdf_is_rejected_safely(api_client):
    truncated = _build_pdf()[:40]  # keeps the %PDF- header, drops everything after
    response = _upload(
        api_client, filename="broken.pdf", content=truncated, content_type="application/pdf"
    )
    assert response.status_code == 400


# 17. Image-only PDF -> explicit error, no OCR attempted.
def test_image_only_pdf_reports_honest_failure(api_client):
    response = _upload(
        api_client,
        filename="scan.pdf",
        content=_build_image_only_pdf(),
        content_type="application/pdf",
    )
    assert response.status_code == 400
    assert "chỉ chứa hình ảnh" in response.json()["message"]


# 18. Encrypted PDF -> explicit error.
def test_encrypted_pdf_reports_honest_failure(api_client):
    response = _upload(
        api_client,
        filename="secret.pdf",
        content=_build_encrypted_pdf(),
        content_type="application/pdf",
    )
    assert response.status_code == 400
    assert "mã hóa" in response.json()["message"]


# 19. Filename path traversal -> still sanitized regardless of the new byte
# sniffing (defense in depth, existing sanitizer behavior unchanged).
def test_path_traversal_filename_is_still_sanitized(api_client):
    response = _upload(
        api_client,
        filename="../../etc/passwd.txt",
        content=b"harmless content",
        content_type="text/plain",
    )
    assert response.status_code == 201
    source_name = response.json()["document"]["source_name"]
    assert "/" not in source_name
    assert ".." not in source_name


# 20. Error responses never echo raw bytes, file content, or an internal
# parser path back to the caller.
@pytest.mark.parametrize(
    "filename,content,content_type",
    [
        ("fake.pdf", b"This is just plain text, not a PDF.", "application/pdf"),
        ("notes.txt", bytes(range(256)) * 4, "text/plain"),
        ("malware.pdf", b"PK\x03\x04" + bytes(range(256)) * 4, "application/pdf"),
    ],
)
def test_mismatch_error_bodies_do_not_contain_uploaded_content(
    api_client, filename, content, content_type
):
    response = _upload(api_client, filename=filename, content=content, content_type=content_type)
    assert response.status_code == 415
    body = response.text
    assert filename not in body
    # A generic, static message only - never the raw bytes or a hex dump.
    assert "không khớp với loại đã khai báo" in body or "Không thể nhận dạng" in body
