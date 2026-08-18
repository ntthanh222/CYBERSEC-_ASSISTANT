# Phase 2.6 — Knowledge Ingestion Pipeline

## Supported formats

| Format | Extraction | Notes |
|---|---|---|
| `.txt` | UTF-8 decode | Rejects invalid UTF-8 and empty/whitespace-only content. |
| `.md` / `.markdown` | Split into sections by heading (`#`–`######`), each section keeps its nearest heading as metadata | No heading → one section, `heading=None`. |
| `.pdf` (text layer) | `pypdf`, one section per page with real extractable text | Pages with no extractable text are skipped; **image-only (scanned) PDFs are rejected with an explicit, honest error — no OCR is run.** Encrypted PDFs are rejected. |

MIME/type detection (`backend/services/knowledge_extraction.py:detect_kind`)
is **byte-first**: the actual upload bytes are sniffed (a real `%PDF-`
magic header, or content that decodes cleanly as safe UTF-8 text) and that
sniffed result is what the extractor acts on. The client-declared
`Content-Type` and filename extension are never trusted on their own — they
are used only to disambiguate TXT vs Markdown once the bytes are already
confirmed to be text, and as a consistency check that hard-rejects the
upload (`UnsupportedMediaTypeError`, 415) when they contradict the sniffed
bytes. See `docs/RAG_SECURITY.md` for the full mismatch-policy table and the
history of why this replaced the original declared-type-first design.
Extraction failure (a mismatched-but-sniffable kind that still fails to
parse, e.g. a malformed PDF) raises `InvalidRequestError` (400); there is no
silent "best effort" fallback for either failure mode.

## Pipeline

```
KnowledgeService.ingest()  (backend/services/knowledge.py)
  1. size check (RAG_MAX_UPLOAD_BYTES) -> PayloadTooLargeError (413)
  2. empty-file check -> InvalidRequestError (400)
  3. filename sanitized (path components/control chars stripped, never
     used to open a path - the raw upload is processed entirely in memory,
     never written to disk, so there is no path-traversal surface at all)
  4. detect_kind (byte-level sniffing) -> UnsupportedMediaTypeError (415)
     on unrecognizable bytes or a declared-type/extension mismatch;
     extract -> InvalidRequestError (400) on any unparseable/empty/
     oversized-page-count input. Both happen before any document row is
     created - a rejected upload never leaves a row behind.
  5. checksum = sha256(joined extracted section text)   [not raw bytes -
     the same content re-saved under a different format is still a
     duplicate]
  6. idempotency: an existing ready/processing document with the same
     (owner, checksum) is returned as-is (reused_existing=True) instead of
     re-ingesting
  7. document row created, status=processing, COMMITTED immediately (the
     caller gets an id right away even for a slow document)
  8. chunk_sections() -> embed(batch) -> replace_chunks() (delete-then-
     insert inside one flush) -> mark_ready() -> COMMIT
     - any exception before the final commit rolls the session back
       (discarding any added-but-uncommitted chunk rows - zero partial
       chunks ever persist) and instead calls mark_failed() with a safe,
       author-written error message, committed on its own
```

A document therefore always ends in exactly one of two states with a fully
consistent chunk set: `ready` with `chunk_count` chunks actually present, or
`failed` with zero chunks and a safe `error_message`. It is never left
`ready` with a partial chunk set.

## Limits (all configurable, `backend/config/settings.py`)

| Setting | Default | Purpose |
|---|---|---|
| `RAG_MAX_UPLOAD_BYTES` | 15,000,000 | Hard cap on upload size (413 over). |
| `RAG_MAX_PAGES` | 300 | PDF page-count cap (rejected before extraction proceeds). |
| `RAG_MAX_CHUNKS_PER_DOCUMENT` | 2000 | Guards against pathological chunk explosion. |
| `RAG_CHUNK_SIZE_CHARS` | 1200 | Target chunk size (soft — see below). |
| `RAG_CHUNK_OVERLAP_CHARS` | 200 | Character overlap carried into the next chunk. |
| `RAG_MIN_CHUNK_CHARS` | 40 | Trailing under-sized chunks merge into the previous one instead of being dropped. |

## Chunking (`backend/services/knowledge_chunking.py`)

- Never crosses a section boundary — a Markdown heading or a PDF page is
  always a chunk boundary too, so every chunk's metadata can name exactly
  one page and/or heading.
- Within a section: paragraphs are packed greedily up to the target chunk
  size; a paragraph longer than the target is split on sentence
  boundaries first. A single unit (sentence) longer than the target still
  becomes its own oversized chunk rather than being cut mid-word — cutting
  inside a word, including a multi-byte Vietnamese character, is worse
  than one oversized chunk.
- Overlap is measured in characters and re-aligned to whole sentences, so
  it never starts mid-sentence.
- Unicode (including Vietnamese diacritics) passes through untouched —
  only ASCII whitespace is normalized.

Tested explicitly (`backend/tests/test_knowledge_chunking.py`,
`test_knowledge_extraction.py`): short documents, long documents (target
enforced within slack), Vietnamese Unicode content, Markdown headings, PDF
multi-page extraction with real page numbers, empty content (rejected),
duplicate upload (idempotent, verified end-to-end with a real embedding
model against both local and hosted Postgres).

## Reprocessing

`POST /api/knowledge/documents/{id}/reprocess` re-chunks and re-embeds a
document using its **already-stored chunk content** (each existing chunk
becomes a pseudo-section, keeping its page/heading), not the original
uploaded bytes — the raw file is never retained after ingestion. This is
the real, useful case for reprocessing: a changed chunk-size/overlap
config or a redeployed embedding model. Recovering from a first-attempt
failure has nothing to reprocess from and must be re-uploaded.

## Security properties

See `docs/RAG_SECURITY.md` for the full model. Summary relevant to
ingestion specifically:

- No temp files, no disk writes of the upload — no path-traversal surface.
- Filename is sanitized (basename only, control characters stripped) even
  though it is never used as a path, so it can never corrupt a log line or
  response either.
- MIME type is determined by sniffing the actual bytes (a real `%PDF-`
  header, or content that decodes as safe UTF-8 text), not trusted from
  the client header or filename extension alone. A ZIP/EXE/image renamed
  to `.pdf`, a real PDF re-labelled `text/plain`, or plain text renamed to
  `.pdf` are all hard-rejected with 415 before any extraction is attempted.
- No archive/zip formats are supported in this phase — no zip-bomb surface
  exists to defend against.
- Uploaded content is never executed in any sense — only extracted as
  text.
