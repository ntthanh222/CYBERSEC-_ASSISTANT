"""Local Query Normalization for RAG Local-First.

Performs deterministic local normalization without calling external AI models:
- Unicode normalization (NFKC)
- Whitespace and punctuation cleaning
- Vietnamese diacritics normalization & accent preservation
- Cybersecurity alias mapping (e.g. vuln/lỗ hổng -> vulnerability, ioc/chỉ số -> indicator)
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Set

_ALIAS_MAP: Dict[str, str] = {
    "vuln": "vulnerability",
    "vulns": "vulnerabilities",
    "lo hong": "vulnerability",
    "lỗ hổng": "vulnerability",
    "diem yeu": "vulnerability",
    "điểm yếu": "vulnerability",
    "ioc": "indicator_of_compromise",
    "iocs": "indicators_of_compromise",
    "cve": "cve_identifier",
    "incident": "security_incident",
    "su co": "security_incident",
    "sự cố": "security_incident",
    "alert": "security_alert",
    "canh bao": "security_alert",
    "cảnh báo": "security_alert",
    "asset": "system_asset",
    "tai san": "system_asset",
    "tài sản": "system_asset",
    "host": "hostname",
    "domain": "domain_name",
    "ten mien": "domain_name",
    "tên miền": "domain_name",
    "mitre": "mitre_attck",
    "ttp": "technique_tactic_procedure",
    "cvss": "cvss_score",
    "severity": "severity_level",
    "muc do": "severity_level",
    "mức độ": "severity_level",
    "critical": "critical_severity",
    "high": "high_severity",
    "medium": "medium_severity",
    "low": "low_severity",
}


#: Common Vietnamese incident-response/policy vocabulary mapped to plain
#: English equivalents. Uploaded knowledge-base documents are frequently
#: written in English while users ask about them in Vietnamese; neither the
#: embedding model's cross-lingual alignment nor a raw substring/full-text
#: match can be relied on alone for short policy fragments like "isolated
#: within 15 minutes" or "approved by the Security Manager". This glossary
#: is deliberately domain-scoped (security/policy terms), not a general
#: translator - it exists purely to bridge retrieval/extractive-matching
#: across the language boundary, never to alter what is shown to the user.
_VI_EN_TERM_GLOSSARY: Dict[str, str] = {
    "cô lập": "isolate isolated isolation",
    "co lap": "isolate isolated isolation",
    "khôi phục": "recovery recover restore",
    "khoi phuc": "recovery recover restore",
    "phê duyệt": "approve approved approval",
    "phe duyet": "approve approved approval",
    "hệ thống": "system",
    "he thong": "system",
    "mật khẩu": "password",
    "mat khau": "password",
    "phút": "minute minutes",
    "phut": "minute minutes",
    "giờ": "hour hours",
    "gio": "hour hours",
    "bao lâu": "how long duration",
    "bao lau": "how long duration",
    "quản lý bảo mật": "security manager",
    "quan ly bao mat": "security manager",
}


def expand_query_terms(query: str) -> str:
    """Append plain-English equivalents of common Vietnamese security/policy
    terms found in ``query`` to the end of it.

    Used only for retrieval and extractive term-matching - the returned
    string is never shown to the user. This lets a Vietnamese follow-up
    ("Ai phê duyệt việc khôi phục hệ thống?") match an English document
    sentence ("System recovery must be approved by the Security Manager")
    that shares no literal Vietnamese words with the query.
    """
    lowered = (query or "").lower()
    if not lowered:
        return query
    no_accent = strip_vietnamese_accents(lowered)
    # Each concept has both an accented and an accent-stripped key (e.g.
    # "cô lập" / "co lap") pointing at the same translation - matching
    # against both `lowered` and `no_accent` would otherwise append that
    # translation twice. A set on the translation text itself dedupes
    # regardless of which key(s) matched.
    extra: "dict[str, None]" = {}
    for phrase, translation in _VI_EN_TERM_GLOSSARY.items():
        if phrase in lowered or phrase in no_accent:
            extra.setdefault(translation, None)
    if not extra:
        return query
    return f"{query} {' '.join(extra)}"


@dataclass(frozen=True)
class NormalizedQuery:
    original_query: str
    normalized_query: str
    cleaned_tokens: List[str]
    detected_aliases: Set[str] = field(default_factory=set)


def strip_vietnamese_accents(text: str) -> str:
    """Utility to convert accented Vietnamese chars to ASCII equivalent for fuzzy/alias matching."""
    s1 = unicodedata.normalize("NFD", text)
    s2 = "".join(c for c in s1 if unicodedata.category(c) != "Mn")
    return s2.replace("đ", "d").replace("Đ", "D")


def normalize_query(query: str) -> NormalizedQuery:
    """Normalize user input text deterministically."""
    raw = (query or "").strip()
    if not raw:
        return NormalizedQuery(original_query="", normalized_query="", cleaned_tokens=[])

    # 1. Unicode NFKC
    text = unicodedata.normalize("NFKC", raw)

    # 2. Lowercase for mapping (preserving raw for case-sensitive needs if any)
    lower_text = text.lower()

    # 3. Detect cybersec aliases
    detected_aliases: Set[str] = set()
    no_accent_text = strip_vietnamese_accents(lower_text)

    for alias, canonical in _ALIAS_MAP.items():
        if alias in lower_text or alias in no_accent_text:
            detected_aliases.add(canonical)

    # 4. Whitespace cleanup
    cleaned_text = re.sub(r"\s+", " ", lower_text).strip()
    tokens = [t for t in re.split(r"[^\w\-\.]+", cleaned_text) if t]

    return NormalizedQuery(
        original_query=raw,
        normalized_query=cleaned_text,
        cleaned_tokens=tokens,
        detected_aliases=detected_aliases,
    )
