"""Hybrid-retrieval building blocks: exact-match detection, MMR, local rerank.

Pure functions, deliberately independent of the database/embedding provider
so they are fully unit-testable without Postgres or a real model. Combined
with pgvector cosine search and PostgreSQL full-text search in
:mod:`backend.services.rag_retrieval`, per FINAL_MASTER_PROMPT_CYBERSEC_
ASSISTANT.md section F: "hybrid search: pgvector semantic; PostgreSQL
full-text; exact-match ưu tiên cho CVE, IP, domain, hash, port, MITRE
technique. ... Deduplicate + MMR. Local reranker."

The MMR/rerank diversity signal here is lexical (token-set Jaccard), not a
second embedding call - cheaper, and MMR's diversity term does not need to
use the same similarity metric as the relevance term it is trading off
against. This is a deliberate, documented simplification, not an oversight.
"""
from __future__ import annotations

import re
from typing import Any, Sequence

# --- Exact-match term extraction --------------------------------------------

_CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_HASH_RE = re.compile(r"\b[a-fA-F0-9]{32}\b|\b[a-fA-F0-9]{40}\b|\b[a-fA-F0-9]{64}\b")
_MITRE_RE = re.compile(r"\bT\d{4}(?:\.\d{3})?\b", re.IGNORECASE)
_PORT_RE = re.compile(r"\bport\s+(\d{1,5})\b", re.IGNORECASE)
_DOMAIN_RE = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"(?:com|net|org|io|gov|edu|mil|co|info|biz|local|invalid)\b",
    re.IGNORECASE,
)


def extract_exact_match_terms(query: str) -> list[str]:
    """Literal tokens worth an exact (not semantic) match: CVE IDs, IPv4
    addresses, file hashes, MITRE ATT&CK technique IDs, port numbers, and
    domain-shaped tokens. Order-preserving, deduplicated, case-preserved
    (the SQL layer does the case-insensitive match)."""
    found: list[str] = []
    for pattern in (_CVE_RE, _IPV4_RE, _HASH_RE, _MITRE_RE, _DOMAIN_RE):
        found.extend(m.group(0) for m in pattern.finditer(query))
    found.extend(m.group(1) for m in _PORT_RE.finditer(query))
    seen: set[str] = set()
    deduped = []
    for term in found:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(term)
    return deduped


# --- Lexical similarity (MMR's diversity term + the local reranker) --------

_WORD_RE = re.compile(r"[a-zA-Z0-9]+")


def _tokenize(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    if intersection == 0:
        return 0.0
    return intersection / len(a | b)


# --- Local reranker ----------------------------------------------------------


#: Added to a candidate's score when the user's query names the document's
#: own title outright (e.g. "theo tài liệu Prompt Injection Test Doc, ...").
#: A short/sparse document can score low on semantic similarity alone even
#: when the user has unambiguously identified it by name - this is a
#: deterministic, high-confidence signal the vector/full-text score can miss.
_TITLE_MATCH_BOOST = 0.35


def rerank_candidates(
    candidates: Sequence[dict[str, Any]],
    *,
    query: str,
    relevance_key: str = "relevance",
    lexical_weight: float = 0.25,
) -> list[dict[str, Any]]:
    """Re-scores each candidate by blending its existing relevance (vector/
    text-rank/exact-match combined score, already 0-1) with a lexical
    term-overlap signal the embedding model alone can miss (exact
    terminology reuse - a real, cheap, in-process reranking signal, not a
    second network call). Returns candidates sorted by the new score,
    descending, each with a ``rerank_score`` field added.
    """
    query_terms = _tokenize(query)
    reranked = []
    for candidate in candidates:
        content_terms = _tokenize(str(candidate.get("content", "")))
        overlap = _jaccard(query_terms, content_terms)
        base = float(candidate.get(relevance_key, 0.0))
        score = (1 - lexical_weight) * base + lexical_weight * overlap

        title_terms = _tokenize(str(candidate.get("title", "")))
        if len(title_terms) >= 2 and title_terms.issubset(query_terms):
            score = min(1.0, score + _TITLE_MATCH_BOOST)

        reranked.append({**candidate, "rerank_score": round(score, 4)})
    reranked.sort(key=lambda c: c["rerank_score"], reverse=True)
    return reranked


# --- MMR (Maximal Marginal Relevance) diversification -----------------------


#: Below this Jaccard overlap, two chunks are "merely on the same topic",
#: not redundant - verified empirically (real demo corpus: two chunks
#: discussing the same CVE from different angles overlap at ~0.22-0.24,
#: while an actual near-duplicate pair - the same fact restated - overlaps
#: at 0.5+). Only real redundancy should cost a candidate its rank; MMR
#: penalizing merely-related content on a small corpus was actively pushing
#: the single correct citation for a specific-fact question out of the
#: final top-k in favor of a less relevant but more "diverse" chunk.
_REDUNDANCY_THRESHOLD = 0.35


def mmr_select(
    candidates: Sequence[dict[str, Any]],
    *,
    k: int,
    relevance_key: str = "rerank_score",
    lambda_param: float = 0.65,
) -> list[dict[str, Any]]:
    """Greedily selects up to ``k`` candidates trading relevance off against
    diversity from what's already been picked, so near-duplicate chunks
    (the same fact restated across two documents) don't crowd out distinct
    information. ``lambda_param`` close to 1 favors relevance, close to 0
    favors diversity - 0.65 keeps relevance dominant while still
    penalizing near-duplicates. The diversity penalty only applies above
    ``_REDUNDANCY_THRESHOLD`` - see its docstring for why.
    """
    remaining = list(candidates)
    selected: list[dict[str, Any]] = []
    selected_terms: list[set[str]] = []

    while remaining and len(selected) < k:
        best_index = -1
        best_score = float("-inf")
        for index, candidate in enumerate(remaining):
            relevance = float(candidate.get(relevance_key, 0.0))
            if selected_terms:
                content_terms = _tokenize(str(candidate.get("content", "")))
                max_overlap = max(_jaccard(content_terms, s) for s in selected_terms)
                diversity_penalty = max_overlap if max_overlap >= _REDUNDANCY_THRESHOLD else 0.0
            else:
                diversity_penalty = 0.0
            score = lambda_param * relevance - (1 - lambda_param) * diversity_penalty
            if score > best_score:
                best_score, best_index = score, index

        chosen = remaining.pop(best_index)
        selected.append(chosen)
        selected_terms.append(_tokenize(str(chosen.get("content", ""))))

    return selected
