"""Secret redaction for text that is about to be persisted or logged.

``docs/05_DATA_MODEL.md`` requires that chat content is redacted *before* it is
stored, and that no password, token, API key or secret ever reaches the
history/audit tables. The structured-log formatter
(:mod:`backend.core.logging`) already redacts by *field name*; this module is
the complementary defence for free-form prose, where a secret arrives inside a
sentence rather than in a named field.

The patterns are deliberately conservative and over-match rather than
under-match: losing a few characters of a user's message is a far cheaper
mistake than persisting a live credential.
"""
import re
from typing import Final

REDACTED: Final = "[REDACTED]"

_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    # PEM private key blocks (whole block, not just the header).
    re.compile(
        r"-----BEGIN[A-Z ]*PRIVATE KEY-----.*?-----END[A-Z ]*PRIVATE KEY-----",
        re.DOTALL | re.IGNORECASE,
    ),
    # JSON Web Tokens.
    re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b"),
    # HTTP bearer/basic credentials.
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
    # Cloud/provider key formats.
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    # Connection strings that embed a password.
    re.compile(
        r"\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s:/@]+:[^\s@]+@\S+",
        re.IGNORECASE,
    ),
    # "key: value" / "password=value" assignments.
    re.compile(
        r"(?i)\b(?:api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|secret[_-]?key"
        r"|client[_-]?secret|password|passwd|pwd|token|secret)\b\s*[:=]\s*[\"']?[^\s\"',;]{4,}"
    ),
)


def redact_text(value: str) -> str:
    """Return ``value`` with any secret-shaped substring replaced."""
    if not value:
        return value
    redacted = value
    for pattern in _PATTERNS:
        redacted = pattern.sub(REDACTED, redacted)
    return redacted


def contains_secret(value: str) -> bool:
    """True when :func:`redact_text` would change ``value``."""
    return redact_text(value) != value
