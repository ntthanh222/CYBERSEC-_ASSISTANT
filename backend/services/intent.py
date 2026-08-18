"""Intent classification foundation.

A deliberately simple, deterministic, rule-based classifier. It exists to
establish the *seam* that a real NLU component (Rasa) or a retrieval layer
would later plug into - ``classify`` is the only thing the orchestrator calls,
so swapping the implementation does not touch the routing code.

It is rule-based on purpose: the blueprint requires that a response is never
labelled as coming from a model that did not produce it, and a deterministic
classifier keeps the reported ``intent`` honest and testable. Both Vietnamese
and English keywords are recognised because the product is bilingual.
"""
import re
from enum import Enum
from typing import Final


class Intent(str, Enum):
    GREETING = "greeting"
    DEFINITION = "definition"
    CVE_QUESTION = "cve_question"
    URL_QUESTION = "url_question"
    PASSWORD_QUESTION = "password_question"  # nosec B105
    INCIDENT_RESPONSE = "incident_response"
    KNOWLEDGE_RAG = "knowledge_rag"
    SQLI_QUESTION = "sqli_question"
    SSRF_QUESTION = "ssrf_question"
    CSP_QUESTION = "csp_question"
    GENERAL = "general"


#: Recognised by a dedicated pattern rather than a keyword list, because a bare
#: CVE identifier anywhere in the message is a decisive signal.
_CVE_PATTERN: Final = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE)
_URL_PATTERN: Final = re.compile(r"\bhttps?://\S+", re.IGNORECASE)

_GREETING_KEYWORDS: Final = (
    "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
    "xin chao", "xin chào", "chao ban", "chào bạn", "chao anh", "chào anh",
)
#: Word-boundary matching, not plain substring - "hi" as a bare substring
#: false-positives inside ordinary Vietnamese words like "khi" ("when"),
#: "thi" ("exam"), "chi" ("only/spend"), misclassifying real questions as
#: greetings.
_GREETING_PATTERN: Final = re.compile(
    r"\b(?:" + "|".join(re.escape(keyword) for keyword in _GREETING_KEYWORDS) + r")\b",
    re.IGNORECASE,
)
_DEFINITION_KEYWORDS: Final = (
    "what is", "what are", "define", "definition", "explain", "meaning of",
    "la gi", "là gì", "nghia la", "nghĩa là", "giai thich", "giải thích",
    "dinh nghia", "định nghĩa",
)
_CVE_KEYWORDS: Final = (
    "cve", "vulnerability", "cvss", "lo hong", "lỗ hổng", "diem yeu", "điểm yếu",
)
_URL_KEYWORDS: Final = (
    "url", "link", "website", "domain", "phishing", "duong dan", "đường dẫn",
    "trang web", "ten mien", "tên miền", "lua dao", "lừa đảo",
)
_PASSWORD_KEYWORDS: Final = (
    "password", "passphrase", "credential", "mat khau", "mật khẩu",
    "matkhau", "do manh mat khau", "độ mạnh mật khẩu",
)
#: SQL Injection has its own intent so a follow-up question about it never
#: falls through to GENERAL and becomes eligible for stale CVE/URL carry-forward.
_SQLI_KEYWORDS: Final = (
    "sql injection", "sqli", "sql-injection", "chen sql", "chèn sql",
    "tiem sql", "tiêm sql", "injection sql",
)
#: Server-Side Request Forgery.
_SSRF_KEYWORDS: Final = (
    "ssrf", "server-side request forgery", "server side request forgery",
    "gia mao yeu cau phia server", "giả mạo yêu cầu phía server",
)
#: Content-Security-Policy.
_CSP_KEYWORDS: Final = (
    "csp", "content security policy", "content-security-policy",
    "chinh sach bao mat noi dung", "chính sách bảo mật nội dung",
)
#: Explicit references to an uploaded document / the Knowledge Base. These
#: must force RAG retrieval rather than falling through to app-data tools or
#: general local knowledge, so the user's own material is what gets cited.
_KNOWLEDGE_RAG_KEYWORDS: Final = (
    "theo tai lieu", "theo tài liệu", "tai lieu vua", "tài liệu vừa",
    "tai lieu toi vua", "tài liệu tôi vừa", "vua upload", "vừa upload",
    "vua tai len", "vừa tải lên", "file vua", "file vừa", "trong file",
    "knowledge base", "trong tai lieu", "trong tài liệu",
)
#: An explicit instruction to stop grounding on the previous document/RAG
#: context. Checked before _KNOWLEDGE_RAG_KEYWORDS because the override
#: phrase itself often contains a knowledge-base keyword as a substring
#: (e.g. "bỏ qua tài liệu vừa rồi" contains "tài liệu vừa"), which would
#: otherwise force RAG grounding right after the user asked to stop using it.
_IGNORE_DOCUMENT_KEYWORDS: Final = (
    "bo qua tai lieu", "bỏ qua tài liệu", "khong dung tai lieu",
    "không dùng tài liệu", "quen tai lieu", "quên tài liệu",
    "khong can tai lieu", "không cần tài liệu",
    "ignore the document", "ignore that document", "ignore the previous document",
    "ignore the uploaded document", "without the document", "forget the document",
)
#: Signals that the user believes an asset is actively/recently compromised -
#: this must route to incident-response guidance, never a phishing/URL-scan
#: template.
_INCIDENT_RESPONSE_KEYWORDS: Final = (
    "bi tan cong", "bị tấn công", "nghi bi tan cong", "nghi bị tấn công",
    "bi hack", "bị hack", "bi xam nhap", "bị xâm nhập",
    "bi xam pham", "bị xâm phạm", "da bi tan cong", "đã bị tấn công",
    "compromised", "under attack", "has been hacked", "was hacked",
)


def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(needle in haystack for needle in needles)


def classify(message: str) -> Intent:
    """Classify a user message into a coarse :class:`Intent`.

    Ordering matters: the most specific, highest-confidence signals are tested
    first so that "what is CVE-2021-44228?" is a CVE question rather than a
    generic definition request.
    """
    text = (message or "").strip().lower()
    if not text:
        return Intent.GENERAL

    # Highest priority: an explicit reference to the user's own uploaded
    # material must force RAG grounding, overriding CVE/URL pattern hits
    # that might also appear in the same sentence - unless the user has just
    # explicitly told the assistant to stop using that document.
    if not _contains_any(text, _IGNORE_DOCUMENT_KEYWORDS) and _contains_any(
        text, _KNOWLEDGE_RAG_KEYWORDS
    ):
        return Intent.KNOWLEDGE_RAG
    # A compromise claim must route to incident response, not a generic
    # phishing/URL-scan template, even when the message also contains a URL.
    if _contains_any(text, _INCIDENT_RESPONSE_KEYWORDS):
        return Intent.INCIDENT_RESPONSE
    # SQLi/SSRF/CSP each get a dedicated intent so a message about one of
    # these topics is never left as GENERAL - which would make it eligible
    # for the "stale CVE from a previous turn" context carry-forward below.
    if _contains_any(text, _SQLI_KEYWORDS):
        return Intent.SQLI_QUESTION
    if _contains_any(text, _SSRF_KEYWORDS):
        return Intent.SSRF_QUESTION
    if _contains_any(text, _CSP_KEYWORDS):
        return Intent.CSP_QUESTION
    if _CVE_PATTERN.search(text):
        return Intent.CVE_QUESTION
    if _URL_PATTERN.search(text):
        return Intent.URL_QUESTION
    if _contains_any(text, _PASSWORD_KEYWORDS):
        return Intent.PASSWORD_QUESTION
    if _contains_any(text, _CVE_KEYWORDS):
        return Intent.CVE_QUESTION
    if _contains_any(text, _URL_KEYWORDS):
        return Intent.URL_QUESTION
    # A greeting only counts when the message is short: "hi" is a greeting,
    # a 300-character incident report that happens to contain "hi" is not.
    if len(text) <= 40 and _GREETING_PATTERN.search(text):
        return Intent.GREETING
    if _contains_any(text, _DEFINITION_KEYWORDS):
        return Intent.DEFINITION
    return Intent.GENERAL
