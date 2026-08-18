"""Text chunking for Phase 2.6 knowledge ingestion.

Splits already-extracted text into overlapping, boundary-aware chunks ready
for embedding. Chunking never crosses a section boundary (a Markdown heading
or a PDF page): each chunk's metadata must be able to name exactly one page
and/or heading, so a section boundary is always a chunk boundary too.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

#: Matches a sentence end (Latin and CJK/full-width punctuation) followed by
#: whitespace. Vietnamese text uses standard Latin punctuation, so no special
#: casing is needed for it specifically.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…。！？])\s+")
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")
_WHITESPACE_RUN = re.compile(r"[ \t]+")


@dataclass(frozen=True)
class ExtractedSection:
    """One logically-contiguous piece of extracted text plus its provenance."""

    text: str
    page_number: Optional[int] = None
    heading: Optional[str] = None


@dataclass(frozen=True)
class TextChunk:
    content: str
    character_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)


def normalize_text(text: str) -> str:
    """Collapse runs of horizontal whitespace and stray carriage returns.

    Only ASCII whitespace is touched - Unicode content, including Vietnamese
    diacritics, passes through byte-for-byte.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE_RUN.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def _split_sentences(paragraph: str) -> List[str]:
    parts = [part.strip() for part in _SENTENCE_BOUNDARY.split(paragraph) if part.strip()]
    return parts or ([paragraph] if paragraph.strip() else [])


def _split_paragraphs(text: str) -> List[str]:
    return [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]


def _pack_units(units: Sequence[str], *, chunk_size: int, overlap: int) -> List[str]:
    """Greedily pack whitespace-joinable text units (sentences) into chunks.

    ``chunk_size`` is a target, not a hard ceiling: a single unit longer than
    it becomes its own oversized chunk rather than being cut mid-word (or
    mid multi-byte character), which would corrupt Unicode text.
    """
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for unit in units:
        unit_len = len(unit)
        if current and current_len + 1 + unit_len > chunk_size:
            chunks.append(" ".join(current))
            if overlap > 0:
                carry: List[str] = []
                carry_len = 0
                for prev_unit in reversed(current):
                    if carry_len + len(prev_unit) > overlap:
                        break
                    carry.insert(0, prev_unit)
                    carry_len += len(prev_unit) + 1
                current = carry
                current_len = sum(len(u) for u in current) + max(len(current) - 1, 0)
            else:
                current = []
                current_len = 0
        current.append(unit)
        current_len += unit_len + (1 if len(current) > 1 else 0)

    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_section(
    section: ExtractedSection,
    *,
    chunk_size: int,
    overlap: int,
    min_chunk_chars: int,
) -> List[TextChunk]:
    normalized = normalize_text(section.text)
    if not normalized:
        return []

    units: List[str] = []
    for paragraph in _split_paragraphs(normalized):
        if len(paragraph) <= chunk_size:
            units.append(paragraph)
        else:
            units.extend(_split_sentences(paragraph))

    raw_chunks = _pack_units(units, chunk_size=chunk_size, overlap=overlap)

    # A chunk shorter than the minimum is merged into the previous one rather
    # than dropped, so short trailing content is never silently lost.
    # Dropping is only correct when there is nothing to merge into (the
    # section's only chunk) - so that case is kept as-is.
    merged: List[str] = []
    for text in raw_chunks:
        if merged and len(text) < min_chunk_chars:
            merged[-1] = f"{merged[-1]} {text}".strip()
        else:
            merged.append(text)

    chunks: List[TextChunk] = []
    for text in merged:
        metadata: Dict[str, Any] = {}
        if section.page_number is not None:
            metadata["page"] = section.page_number
        if section.heading:
            metadata["heading"] = section.heading
        chunks.append(TextChunk(content=text, character_count=len(text), metadata=metadata))
    return chunks


def chunk_sections(
    sections: Sequence[ExtractedSection],
    *,
    chunk_size: int,
    overlap: int,
    min_chunk_chars: int,
) -> List[TextChunk]:
    """Chunk every section in order, never crossing a section boundary."""
    chunks: List[TextChunk] = []
    for section in sections:
        chunks.extend(
            chunk_section(
                section,
                chunk_size=chunk_size,
                overlap=overlap,
                min_chunk_chars=min_chunk_chars,
            )
        )
    return chunks
