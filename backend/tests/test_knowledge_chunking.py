"""Text chunking: size/overlap behaviour, section boundaries, Unicode."""
from backend.services.knowledge_chunking import (
    ExtractedSection,
    chunk_section,
    chunk_sections,
    normalize_text,
)


def test_short_document_becomes_a_single_chunk():
    chunks = chunk_section(
        ExtractedSection(text="A short note."),
        chunk_size=1200,
        overlap=200,
        min_chunk_chars=40,
    )
    assert len(chunks) == 1
    assert chunks[0].content == "A short note."


def test_empty_section_produces_no_chunks():
    assert chunk_section(
        ExtractedSection(text="   \n\n  "), chunk_size=1200, overlap=200, min_chunk_chars=40
    ) == []


def test_long_document_splits_into_multiple_chunks_within_size_target():
    long_text = "\n\n".join(f"Paragraph {i}. " * 15 for i in range(20))
    chunks = chunk_section(
        ExtractedSection(text=long_text), chunk_size=300, overlap=50, min_chunk_chars=20
    )
    assert len(chunks) > 1
    for chunk in chunks[:-1]:
        # A target, not a hard ceiling - allow a little slack for the last
        # sentence that pushed a chunk over, never a huge blowout.
        assert chunk.character_count <= 300 + 100


def test_overlap_carries_tail_content_into_the_next_chunk():
    long_text = " ".join(f"Sentence number {i} is here." for i in range(40))
    chunks = chunk_section(
        ExtractedSection(text=long_text), chunk_size=200, overlap=60, min_chunk_chars=10
    )
    assert len(chunks) >= 2
    tail_of_first = chunks[0].content[-30:]
    assert any(word in chunks[1].content for word in tail_of_first.split()[-2:])


def test_vietnamese_unicode_content_is_preserved_byte_for_byte():
    text = (
        "Cách ly máy chủ bị nhiễm khỏi mạng nội bộ ngay lập tức. "
        "Vô hiệu hóa các ổ đĩa chia sẻ và thu hồi phiên đăng nhập."
    )
    chunks = chunk_section(
        ExtractedSection(text=text), chunk_size=1200, overlap=200, min_chunk_chars=10
    )
    assert len(chunks) == 1
    assert chunks[0].content == text
    assert "ổ đĩa" in chunks[0].content


def test_markdown_heading_metadata_is_attached_per_section():
    sections = [
        ExtractedSection(text="Intro body.", heading="Introduction"),
        ExtractedSection(text="Details body.", heading="Details"),
    ]
    chunks = chunk_sections(sections, chunk_size=1200, overlap=0, min_chunk_chars=1)
    headings = [chunk.metadata.get("heading") for chunk in chunks]
    assert headings == ["Introduction", "Details"]


def test_pdf_page_metadata_is_attached_per_section():
    sections = [
        ExtractedSection(text="Page one content.", page_number=1),
        ExtractedSection(text="Page two content.", page_number=2),
    ]
    chunks = chunk_sections(sections, chunk_size=1200, overlap=0, min_chunk_chars=1)
    pages = [chunk.metadata.get("page") for chunk in chunks]
    assert pages == [1, 2]


def test_chunking_never_crosses_a_section_boundary():
    sections = [
        ExtractedSection(text="Short A.", page_number=1),
        ExtractedSection(text="Short B.", page_number=2),
    ]
    chunks = chunk_sections(sections, chunk_size=1200, overlap=200, min_chunk_chars=1)
    assert len(chunks) == 2
    assert chunks[0].metadata["page"] == 1
    assert chunks[1].metadata["page"] == 2
    assert "Short B" not in chunks[0].content
    assert "Short A" not in chunks[1].content


def test_short_trailing_chunk_merges_into_previous_instead_of_being_dropped():
    text = ("Sentence one is reasonably long here. " * 8) + "Tiny."
    chunks = chunk_section(
        ExtractedSection(text=text), chunk_size=250, overlap=0, min_chunk_chars=30
    )
    assert all(len(chunk.content) >= 30 or chunk is chunks[0] for chunk in chunks)
    assert "Tiny." in chunks[-1].content


def test_normalize_text_collapses_whitespace_but_keeps_unicode():
    raw = "Line one.\r\n\r\n  Line   two with  \t tiếng Việt.  \r\n"
    normalized = normalize_text(raw)
    assert "\r" not in normalized
    assert "  " not in normalized
    assert "tiếng Việt" in normalized


def test_duplicate_upload_produces_identical_chunk_content():
    text = "Repeated content for idempotency checks."
    first = chunk_section(
        ExtractedSection(text=text), chunk_size=1200, overlap=200, min_chunk_chars=1
    )
    second = chunk_section(
        ExtractedSection(text=text), chunk_size=1200, overlap=200, min_chunk_chars=1
    )
    assert [c.content for c in first] == [c.content for c in second]
