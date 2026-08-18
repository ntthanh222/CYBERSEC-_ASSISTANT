"""Pure-Python hybrid retrieval building blocks: no DB, no embedding model."""
from backend.services.rag_hybrid import extract_exact_match_terms, mmr_select, rerank_candidates


# --- extract_exact_match_terms ----------------------------------------------


def test_extracts_a_cve_id():
    assert extract_exact_match_terms("Tell me about CVE-2021-44228") == ["CVE-2021-44228"]


def test_extracts_an_ipv4_address():
    assert extract_exact_match_terms("Is 192.168.1.1 in the watchlist?") == ["192.168.1.1"]


def test_extracts_a_sha256_hash():
    hash_value = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"[:64]
    assert extract_exact_match_terms(f"Check hash {hash_value}") == [hash_value]


def test_extracts_a_mitre_technique_id():
    assert extract_exact_match_terms("Explain T1059.001 in detail") == ["T1059.001"]


def test_extracts_a_port_number():
    assert extract_exact_match_terms("Why is port 445 open?") == ["445"]


def test_extracts_a_domain():
    assert extract_exact_match_terms("Is malicious-domain.example.com flagged?") == [
        "malicious-domain.example.com"
    ]


def test_deduplicates_case_insensitively():
    terms = extract_exact_match_terms("cve-2021-44228 and CVE-2021-44228 again")
    assert len(terms) == 1


def test_returns_empty_for_a_plain_language_question():
    assert extract_exact_match_terms("What is the current password policy?") == []


def test_extracts_multiple_distinct_terms_in_one_query():
    terms = extract_exact_match_terms("Compare CVE-2021-44228 and T1190 for host 10.0.0.5")
    assert set(terms) == {"CVE-2021-44228", "T1190", "10.0.0.5"}


# --- rerank_candidates -------------------------------------------------------


def test_rerank_boosts_a_candidate_with_high_lexical_overlap():
    # Close base relevance scores, so the lexical-overlap term (weight 0.25)
    # is what decides the order - this isolates the effect being tested,
    # rather than expecting term overlap to override a large relevance gap.
    candidates = [
        {"content": "unrelated content about firewalls and networking", "relevance": 0.55},
        {
            "content": "log4j remote code execution CVE-2021-44228 vulnerability details",
            "relevance": 0.5,
        },
    ]
    reranked = rerank_candidates(candidates, query="CVE-2021-44228 log4j vulnerability")
    assert reranked[0]["content"].startswith("log4j")


def test_rerank_preserves_order_for_equal_overlap():
    candidates = [
        {"content": "alpha beta gamma", "relevance": 0.8},
        {"content": "delta epsilon zeta", "relevance": 0.3},
    ]
    reranked = rerank_candidates(candidates, query="unrelated query terms")
    assert reranked[0]["relevance"] == 0.8


def test_rerank_adds_a_rerank_score_field_without_mutating_input():
    candidates = [{"content": "test content", "relevance": 0.5}]
    reranked = rerank_candidates(candidates, query="test")
    assert "rerank_score" in reranked[0]
    assert "rerank_score" not in candidates[0]


def test_rerank_boosts_a_document_the_query_names_by_title():
    """Regression for a live bug: a short/sparse document scored below the
    evidence engine's relevance floor even when the user explicitly named it
    ("theo tài liệu Prompt Injection Test Doc, ..."), so the answer silently
    fell back to a generic, ungrounded local-knowledge definition instead of
    the actual document. Naming the document by title is a deterministic
    signal that must reliably surface it.
    """
    candidates = [
        {
            "title": "06_playbooks_and_policies.md",
            "content": "risk acceptance policy unrelated to MFA",
            "relevance": 0.30,
        },
        {
            "title": "Prompt Injection Test Doc",
            "content": "MFA is required for all admin accounts",
            "relevance": 0.28,
        },
    ]
    reranked = rerank_candidates(
        candidates,
        query="theo tai lieu Prompt Injection Test Doc, MFA co bat buoc cho admin khong?",
    )
    assert reranked[0]["title"] == "Prompt Injection Test Doc"
    assert reranked[0]["rerank_score"] >= 0.35


def test_rerank_does_not_boost_a_title_the_query_never_names():
    candidates = [{"title": "Prompt Injection Test Doc", "content": "x", "relevance": 0.2}]
    reranked = rerank_candidates(candidates, query="what is SQL injection?")
    assert reranked[0]["rerank_score"] < 0.35


# --- mmr_select ---------------------------------------------------------------


def test_mmr_select_returns_at_most_k_items():
    candidates = [{"content": f"chunk {i}", "rerank_score": 1.0 - i * 0.1} for i in range(10)]
    selected = mmr_select(candidates, k=3)
    assert len(selected) == 3


def test_mmr_select_prefers_relevance_when_lambda_is_high():
    candidates = [
        {"content": "the highest relevance chunk about ransomware", "rerank_score": 0.9},
        {"content": "a completely different chunk about phishing", "rerank_score": 0.8},
    ]
    selected = mmr_select(candidates, k=1, lambda_param=0.99)
    assert selected[0]["rerank_score"] == 0.9


def test_mmr_select_penalizes_near_duplicate_content():
    """Two near-identical high-relevance chunks and one lower-relevance but
    distinct chunk - MMR should not pick both near-duplicates back to back
    when a diverse alternative exists."""
    candidates = [
        {
            "content": "log4j CVE-2021-44228 remote code execution vulnerability",
            "rerank_score": 0.95,
        },
        {
            "content": "log4j CVE-2021-44228 remote code execution vulnerability details",
            "rerank_score": 0.94,
        },
        {
            "content": "completely unrelated content about phishing awareness training",
            "rerank_score": 0.5,
        },
    ]
    selected = mmr_select(candidates, k=2, lambda_param=0.5)
    contents = [c["content"] for c in selected]
    # The second pick should be the distinct chunk, not the near-duplicate.
    assert "phishing" in contents[1]


def test_mmr_select_handles_fewer_candidates_than_k():
    candidates = [{"content": "only one", "rerank_score": 0.5}]
    selected = mmr_select(candidates, k=5)
    assert len(selected) == 1


def test_mmr_select_does_not_penalize_merely_related_content():
    """Regression: two chunks that are only loosely topically related
    (shared vocabulary like a CVE ID, but distinct facts - real overlap
    ~0.22-0.24 on the actual demo corpus) must not be treated as
    redundant. Below the threshold, a candidate's diversity penalty must
    be exactly zero, so a modestly-lower-relevance-but-distinct chunk
    never displaces a clearly relevant one just for being "different"."""
    candidates = [
        {
            "content": "CVE-2021-44228 affects portal.meridian.example with a CVSS score of 10.0",
            "rerank_score": 0.50,
        },
        {
            "content": "The Log4Shell attempt against CVE-2021-44228 was caught by the WAF logs",
            "rerank_score": 0.48,
        },
        {
            "content": "Unrelated ransomware playbook guidance about legal sign-off procedures",
            "rerank_score": 0.47,
        },
    ]
    selected = mmr_select(candidates, k=2, lambda_param=0.65)
    # The second-highest-relevance CVE chunk must still be picked second -
    # not displaced by the lower-relevance unrelated chunk merely for
    # scoring as "more diverse".
    assert "WAF logs" in selected[1]["content"]
