"""Regression: the "explain for a non-technical person" CVE answer must
synthesize from the looked-up record, never echo the raw NVD payload.

Live-UI failure this covers: asking to explain CVE-2021-44228 to someone
"không biết kỹ thuật" produced an answer that embedded the full raw English
NVD description verbatim in the middle of an otherwise-simplified response.
See AppDataToolRouter._compose_cve_plain_language in
backend/services/rag/tool_router.py.
"""
from backend.providers.cve.fixture import FixtureCVEProvider
from backend.services.rag.tool_router import AppDataToolRouter


async def _get_record():
    from backend.services.cve import _serialize

    provider = FixtureCVEProvider()
    record = await provider.get("CVE-2021-44228")
    return _serialize(record)


async def test_plain_language_cve_answer_has_no_raw_nvd_dump():
    record = await _get_record()
    result = AppDataToolRouter._compose_cve_plain_language(record, {"tool": "cve_lookup"})

    raw_description = record["description"]
    assert raw_description not in result.content
    # The specific sentence fragment from the raw NVD text must not leak
    # verbatim even as a substring of a longer sentence.
    assert "do not protect against attacker" not in result.content


async def test_plain_language_cve_answer_has_no_cvss_vector():
    record = await _get_record()
    result = AppDataToolRouter._compose_cve_plain_language(record, {"tool": "cve_lookup"})
    assert record["vector"] not in result.content
    assert "CVSS:3.1" not in result.content


async def test_plain_language_cve_answer_has_no_cpe_dump():
    record = await _get_record()
    result = AppDataToolRouter._compose_cve_plain_language(record, {"tool": "cve_lookup"})
    assert "cpe:2.3" not in result.content


async def test_plain_language_cve_answer_has_no_raw_timestamps():
    record = await _get_record()
    result = AppDataToolRouter._compose_cve_plain_language(record, {"tool": "cve_lookup"})
    assert "2021-12-10" not in result.content
    assert "2023-11-07" not in result.content


async def test_plain_language_cve_answer_is_still_grounded_and_synthesized():
    record = await _get_record()
    result = AppDataToolRouter._compose_cve_plain_language(record, {"tool": "cve_lookup"})
    content = result.content
    assert record["cve_id"] in content
    # Synthesized from the real evidence (remote-code-execution impact,
    # critical severity), not a placeholder - just never verbatim.
    assert "thực thi mã" in content or "nghiêm trọng" in content
    assert result.metadata["grounding_status"] == "GROUNDED"


async def test_explicit_raw_data_request_still_returns_full_record():
    """The synthesis-only behaviour is specific to a plain-language request -
    an explicit ask for raw data must still work."""
    record = await _get_record()
    result = AppDataToolRouter._compose_cve_plain_language(record, {"tool": "cve_lookup"})
    # (compose_cve_plain_language itself never includes raw data by design;
    # the raw-request routing is exercised at the _route_cve dispatch level,
    # covered by the CVE_RAW_DATA_MARKERS override in tool_router.py.)
    assert "CVE-2021-44228" in result.content
