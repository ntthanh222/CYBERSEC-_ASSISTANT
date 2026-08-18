"""Text extraction for Phase 2.6 knowledge ingestion.

Supports TXT, Markdown, and PDFs with a text layer, entirely in memory (the
raw upload is never written to disk, so there is no temp-file path and
nothing to clean up or path-traverse into). A PDF with no extractable text
layer (an image-only scan) is reported as an honest extraction failure - no
OCR is run, by design.

Type detection (:func:`detect_kind`) is byte-first: the actual file content
is sniffed (a real ``%PDF-`` magic header, or content that decodes cleanly as
UTF-8 text) and is the only thing that decides whether a PDF or text
extractor runs. The client-declared ``Content-Type`` and the filename
extension are never trusted on their own - they are used only (a) to choose
between TXT and Markdown once the bytes have already been confirmed to be
text, and (b) as a consistency check that hard-fails the upload when it
contradicts what the bytes actually are (e.g. a ZIP renamed to ``.pdf``, or a
real PDF re-labelled ``text/plain``). See ``docs/RAG_SECURITY.md`` for the
full mismatch-policy table.
"""
import re
from dataclasses import dataclass
from typing import List, Optional

from backend.core.exceptions import InvalidRequestError, UnsupportedMediaTypeError
from backend.services.knowledge_chunking import ExtractedSection

#: Declared upload MIME type -> internal document kind. Only used as a
#: consistency signal against sniffed bytes - see module docstring.
_MIME_TO_KIND = {
    "text/plain": "txt",
    "text/markdown": "markdown",
    "text/x-markdown": "markdown",
    "application/pdf": "pdf",
}
_EXTENSION_TO_KIND = {
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
    ".pdf": "pdf",
}
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")

#: A real PDF's magic header must appear within this many leading bytes.
#: Some PDF producers prepend a few bytes of leading whitespace/comments
#: before ``%PDF-``, so this is intentionally larger than 5 bytes while still
#: bounding how much of a non-PDF file is scanned.
_PDF_HEADER_SEARCH_WINDOW = 1024
_PDF_MAGIC = b"%PDF-"

#: How much of a candidate text file's decoded content is inspected for a
#: suspicious concentration of control characters (a signal that decode()
#: got lucky on what is actually binary data, not real text).
_CONTROL_CHAR_SAMPLE_CHARS = 8192
_MAX_CONTROL_CHAR_RATIO = 0.01
_UTF8_BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class ExtractionResult:
    sections: List[ExtractedSection]
    page_count: Optional[int]


@dataclass(frozen=True)
class DetectedFileKind:
    """The canonical result of byte-level upload type detection.

    ``kind`` is what the rest of the ingestion pipeline acts on. The other
    fields exist only for observability (e.g. audit metadata) and must never
    be echoed into a client-facing error message together with raw content.
    """

    kind: str  # "pdf" | "txt" | "markdown"
    detected_mime: str
    declared_mime: str
    extension: str
    reason: str


def _looks_like_pdf(raw_bytes: bytes) -> bool:
    return _PDF_MAGIC in raw_bytes[:_PDF_HEADER_SEARCH_WINDOW]


def _looks_like_text(raw_bytes: bytes) -> bool:
    """Real byte inspection for "is this safe to treat as UTF-8 text".

    Rejects a NUL byte outright (real text documents never contain one),
    requires a clean UTF-8 decode (no lossy/replacement decoding), and
    rejects content where more than 1% of a sample is a non-whitespace
    control character - the signature of binary data that happened to
    decode as UTF-8 rather than genuine text.
    """
    if b"\x00" in raw_bytes:
        return False
    body = raw_bytes[len(_UTF8_BOM) :] if raw_bytes.startswith(_UTF8_BOM) else raw_bytes
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return False
    sample = text[:_CONTROL_CHAR_SAMPLE_CHARS]
    if not sample:
        return True
    control_count = sum(1 for ch in sample if ord(ch) < 32 and ch not in "\t\n\r")
    return (control_count / len(sample)) <= _MAX_CONTROL_CHAR_RATIO


def detect_kind(raw_bytes: bytes, mime_type: str, filename: str) -> DetectedFileKind:
    """Determine the document kind from real file bytes.

    Bytes are the source of truth. ``mime_type``/``filename`` are only
    allowed to (a) disambiguate TXT vs Markdown once the bytes are already
    confirmed to be text, and (b) trigger a hard 415 rejection when they
    contradict the sniffed bytes (e.g. PDF bytes declared as ``text/plain``,
    or text content named ``*.pdf``). A generic/missing declared type never
    blocks an otherwise-valid detection, and an unrecognized declared type
    alone is never sufficient to accept a file bytes-sniffing rejects.
    """
    declared_mime = (mime_type or "").split(";")[0].strip().lower()
    lower_name = (filename or "").lower()
    extension = next(
        (suffix for suffix in _EXTENSION_TO_KIND if lower_name.endswith(suffix)), ""
    )
    declared_kind = _MIME_TO_KIND.get(declared_mime)
    extension_kind = _EXTENSION_TO_KIND.get(extension)

    if _looks_like_pdf(raw_bytes):
        if declared_kind not in (None, "pdf") or extension_kind not in (None, "pdf"):
            raise UnsupportedMediaTypeError(
                "Nội dung tệp tải lên không khớp với loại đã khai báo "
                "hoặc phần mở rộng tên tệp."
            )
        return DetectedFileKind(
            kind="pdf",
            detected_mime="application/pdf",
            declared_mime=declared_mime,
            extension=extension,
            reason="pdf_magic_header",
        )

    if _looks_like_text(raw_bytes):
        if declared_kind == "pdf" or extension_kind == "pdf":
            raise UnsupportedMediaTypeError(
                "Nội dung tệp tải lên không khớp với loại đã khai báo "
                "hoặc phần mở rộng tên tệp."
            )
        kind = "markdown" if declared_kind == "markdown" or extension_kind == "markdown" else "txt"
        return DetectedFileKind(
            kind=kind,
            detected_mime="text/markdown" if kind == "markdown" else "text/plain",
            declared_mime=declared_mime,
            extension=extension,
            reason="utf8_text",
        )

    raise UnsupportedMediaTypeError(
        "Không thể nhận dạng tệp tải lên là một loại được hỗ trợ "
        "(PDF có lớp văn bản, văn bản UTF-8, hoặc tài liệu Markdown UTF-8)."
    )


def extract(*, kind: str, raw_bytes: bytes, max_pages: int) -> ExtractionResult:
    if kind == "txt":
        return _extract_plain_text(raw_bytes)
    if kind == "markdown":
        return _extract_markdown(raw_bytes)
    if kind == "pdf":
        return _extract_pdf(raw_bytes, max_pages=max_pages)
    raise InvalidRequestError("Loại tệp không được hỗ trợ.")


def _decode_text(raw_bytes: bytes) -> str:
    try:
        # utf-8-sig: strips a leading BOM if present (common from Notepad/
        # PowerShell-saved files) instead of decoding it into a literal
        # U+FEFF character that would otherwise leak into the first chunk's
        # stored content and every citation built from it.
        return raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidRequestError("Tệp không phải văn bản UTF-8 hợp lệ.") from exc


def _extract_plain_text(raw_bytes: bytes) -> ExtractionResult:
    text = _decode_text(raw_bytes)
    if not text.strip():
        raise InvalidRequestError("Tài liệu không có nội dung văn bản có thể trích xuất.")
    return ExtractionResult(sections=[ExtractedSection(text=text)], page_count=None)


def _extract_markdown(raw_bytes: bytes) -> ExtractionResult:
    text = _decode_text(raw_bytes)
    if not text.strip():
        raise InvalidRequestError("Tài liệu không có nội dung văn bản có thể trích xuất.")

    sections: List[ExtractedSection] = []
    current_heading: Optional[str] = None
    current_lines: List[str] = []

    def flush() -> None:
        body = "\n".join(current_lines).strip()
        if body:
            sections.append(ExtractedSection(text=body, heading=current_heading))

    for line in text.split("\n"):
        match = _MD_HEADING.match(line.strip())
        if match:
            flush()
            current_lines.clear()
            current_heading = match.group(2).strip()
        else:
            current_lines.append(line)
    flush()

    if not sections:
        raise InvalidRequestError("Tài liệu không có nội dung văn bản có thể trích xuất.")
    return ExtractionResult(sections=sections, page_count=None)


def _extract_pdf(raw_bytes: bytes, *, max_pages: int) -> ExtractionResult:
    import io

    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(raw_bytes))
    except PdfReadError as exc:
        raise InvalidRequestError("Tệp không phải là PDF hợp lệ.") from exc
    except Exception as exc:  # pypdf raises assorted errors for malformed input
        raise InvalidRequestError("Tệp không phải là PDF hợp lệ.") from exc

    if reader.is_encrypted:
        raise InvalidRequestError("Không hỗ trợ PDF được mã hóa.")

    total_pages = len(reader.pages)
    if total_pages > max_pages:
        raise InvalidRequestError(
            f"PDF có quá nhiều trang: chỉ hỗ trợ tối đa {max_pages} trang."
        )

    sections: List[ExtractedSection] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            text = ""
        if text:
            sections.append(ExtractedSection(text=text, page_number=index))

    if not sections:
        raise InvalidRequestError(
            "Không tìm thấy văn bản có thể trích xuất trong PDF này. PDF chỉ chứa hình ảnh "
            "(bản scan) không được hỗ trợ - OCR không được chạy tự động."
        )
    return ExtractionResult(sections=sections, page_count=total_pages)
