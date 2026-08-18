"""Text extraction: TXT/Markdown/PDF, MIME detection, and failure modes."""
import io

import pytest
from reportlab.pdfgen import canvas

from backend.core.exceptions import InvalidRequestError, UnsupportedMediaTypeError
from backend.services.knowledge_extraction import detect_kind, extract


def _build_pdf(pages: list[str]) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(400, 400))
    for page_text in pages:
        pdf.drawString(50, 350, page_text)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_detect_kind_uses_declared_mime_only_to_disambiguate_text_kind():
    assert detect_kind(b"Hello world.", "text/plain", "whatever.bin").kind == "txt"
    assert detect_kind(b"# Heading\nBody.", "text/markdown", "whatever.bin").kind == "markdown"
    pdf_bytes = _build_pdf(["Page."])
    assert detect_kind(pdf_bytes, "application/pdf", "whatever.bin").kind == "pdf"


def test_detect_kind_falls_back_to_extension_when_bytes_agree():
    assert detect_kind(b"# Heading", "application/octet-stream", "notes.md").kind == "markdown"
    assert detect_kind(b"plain text", "application/octet-stream", "notes.txt").kind == "txt"
    pdf_bytes = _build_pdf(["Page."])
    assert detect_kind(pdf_bytes, "", "notes.pdf").kind == "pdf"


def test_detect_kind_rejects_unrecognizable_binary():
    binary = bytes(range(256)) * 4
    with pytest.raises(UnsupportedMediaTypeError):
        detect_kind(binary, "application/zip", "archive.zip")


def test_detect_kind_rejects_pdf_bytes_declared_as_text():
    pdf_bytes = _build_pdf(["Page."])
    with pytest.raises(UnsupportedMediaTypeError):
        detect_kind(pdf_bytes, "text/plain", "notes.txt")


def test_detect_kind_rejects_text_bytes_declared_as_pdf():
    with pytest.raises(UnsupportedMediaTypeError):
        detect_kind(b"Just plain text content.", "application/pdf", "fake.pdf")


def test_detect_kind_rejects_text_renamed_to_pdf_extension():
    with pytest.raises(UnsupportedMediaTypeError):
        detect_kind(b"Just plain text content.", "", "fake.pdf")


def test_detect_kind_accepts_generic_content_type_with_matching_extension_and_bytes():
    pdf_bytes = _build_pdf(["Page."])
    result = detect_kind(pdf_bytes, "application/octet-stream", "report.pdf")
    assert result.kind == "pdf"


def test_detect_kind_rejects_generic_content_type_with_unknown_binary():
    binary = bytes(range(256)) * 4
    with pytest.raises(UnsupportedMediaTypeError):
        detect_kind(binary, "application/octet-stream", "file.bin")


def test_extract_plain_text():
    result = extract(kind="txt", raw_bytes="Hello, world.".encode("utf-8"), max_pages=10)
    assert len(result.sections) == 1
    assert result.sections[0].text == "Hello, world."
    assert result.page_count is None


def test_extract_plain_text_rejects_empty_content():
    with pytest.raises(InvalidRequestError):
        extract(kind="txt", raw_bytes=b"   \n  ", max_pages=10)


def test_extract_plain_text_rejects_invalid_utf8():
    with pytest.raises(InvalidRequestError):
        extract(kind="txt", raw_bytes=b"\xff\xfe\x00bad", max_pages=10)


def test_extract_markdown_splits_by_heading():
    md = "# First\nBody one.\n\n## Second\nBody two.\n"
    result = extract(kind="markdown", raw_bytes=md.encode("utf-8"), max_pages=10)
    assert [s.heading for s in result.sections] == ["First", "Second"]
    assert result.sections[0].text == "Body one."
    assert result.sections[1].text == "Body two."


def test_extract_markdown_with_no_heading_is_one_section():
    md = "Just a paragraph with no heading at all."
    result = extract(kind="markdown", raw_bytes=md.encode("utf-8"), max_pages=10)
    assert len(result.sections) == 1
    assert result.sections[0].heading is None


def test_extract_markdown_vietnamese_content():
    md = "# Ứng phó sự cố\n\nCách ly máy chủ bị nhiễm ngay lập tức.\n"
    result = extract(kind="markdown", raw_bytes=md.encode("utf-8"), max_pages=10)
    assert result.sections[0].heading == "Ứng phó sự cố"
    assert "Cách ly máy chủ" in result.sections[0].text


def test_extract_pdf_with_real_text_layer():
    pdf_bytes = _build_pdf(["Page one text.", "Page two text."])
    result = extract(kind="pdf", raw_bytes=pdf_bytes, max_pages=10)
    assert result.page_count == 2
    assert len(result.sections) == 2
    assert result.sections[0].page_number == 1
    assert "Page one text." in result.sections[0].text
    assert result.sections[1].page_number == 2


def test_extract_pdf_rejects_invalid_file():
    with pytest.raises(InvalidRequestError):
        extract(kind="pdf", raw_bytes=b"not a pdf at all", max_pages=10)


def test_extract_pdf_enforces_max_page_limit():
    pdf_bytes = _build_pdf(["One.", "Two.", "Three."])
    with pytest.raises(InvalidRequestError):
        extract(kind="pdf", raw_bytes=pdf_bytes, max_pages=2)


def test_extract_pdf_with_no_text_layer_reports_honest_failure():
    # A blank page has no extractable text - the same shape a scanned,
    # image-only PDF would produce. No OCR is run; extraction must say so.
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(400, 400))
    pdf.showPage()
    pdf.save()
    with pytest.raises(InvalidRequestError, match="PDF chỉ chứa hình ảnh"):
        extract(kind="pdf", raw_bytes=buffer.getvalue(), max_pages=10)
