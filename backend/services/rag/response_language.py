"""Response-language preference for the AI Assistant.

Platform default is Vietnamese for every canned/local answer (per the
Vietnamese-UI rollout). The only escape hatch is an explicit request for an
English reply in the user's own message - everything else stays Vietnamese,
regardless of what script the question itself was typed in.
"""
from __future__ import annotations

import re

_ENGLISH_REQUEST_RE = re.compile(
    r"(answer|respond|reply)\s+in\s+english"
    r"|in\s+english\s*,?\s*please"
    r"|english\s+please"
    r"|tr[aả]\s*l[oờ]i\s+b[aằ]ng\s+ti[eế]ng\s+anh"
    r"|n[oó]i\s+ti[eế]ng\s+anh",
    re.IGNORECASE,
)


def wants_english(text: str) -> bool:
    """True only when the message explicitly asks for an English reply."""
    return bool(_ENGLISH_REQUEST_RE.search(text or ""))
