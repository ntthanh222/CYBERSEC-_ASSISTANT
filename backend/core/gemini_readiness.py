"""Process-wide Gemini Demo Mode readiness state.

Mirrors ``embedding_readiness.py``'s pattern: a lazily-probed, cached
process-wide state rather than a live external call on every health-check
request. This matters specifically for Gemini because ``DEMO_REQUIRE_GEMINI=
true`` (see ``backend/config/settings.py``) requires READY to mean "a real
``generateContent`` call actually succeeded" - re-running that probe on every
``/api/system/ai-health`` poll would burn the operator's quota just from the
UI's own health pill, and could itself trigger the very RATE_LIMITED state
it's trying to report honestly.

``last_error_category`` is always one of exactly five values, matching
FINAL_MASTER_PROMPT_CYBERSEC_ASSISTANT.md section C.7: NOT_CONFIGURED,
INVALID_KEY, RATE_LIMITED, UNAVAILABLE, DEGRADED. DEGRADED covers a
malformed/unrecognized upstream response - not "no key" or "bad key", a real
answer just didn't come back parseable.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal, Optional

GeminiReadinessStatus = Literal["not_started", "checking", "ready", "failed"]
GeminiErrorCategory = Literal[
    "NOT_CONFIGURED", "INVALID_KEY", "RATE_LIMITED", "UNAVAILABLE", "DEGRADED"
]


@dataclass
class _State:
    status: GeminiReadinessStatus = "not_started"
    model: Optional[str] = None
    model_supported: Optional[bool] = None
    checked_at: Optional[float] = None
    last_error_category: Optional[GeminiErrorCategory] = None


_state = _State()


def mark_checking() -> None:
    _state.status = "checking"


def mark_ready(*, model: str, model_supported: Optional[bool]) -> None:
    _state.status = "ready"
    _state.model = model
    _state.model_supported = model_supported
    _state.checked_at = time.time()
    _state.last_error_category = None


def mark_failed(
    category: GeminiErrorCategory, *, model: Optional[str], model_supported: Optional[bool]
) -> None:
    _state.status = "failed"
    _state.model = model
    _state.model_supported = model_supported
    _state.checked_at = time.time()
    _state.last_error_category = category


def get_gemini_readiness() -> dict:
    return {
        "status": _state.status,
        "model": _state.model,
        "model_supported": _state.model_supported,
        "checked_at": _state.checked_at,
        "last_error_category": _state.last_error_category,
    }


def _reset_for_tests() -> None:
    global _state
    _state = _State()
