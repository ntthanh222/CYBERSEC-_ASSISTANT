"""Process-wide embedding-model readiness state.

The local embedding model (see ``backend/providers/embeddings/local.py``)
loads lazily on first use and can take ~20-90s (ONNX Runtime session init,
plus a one-time Hugging Face download on a genuinely empty cache volume).
Blocking app startup on that would delay `docker compose up`'s healthcheck
for no good reason - the rest of the app (dashboard, security tools, auth)
works fine before the model is warm. Instead this tracks a separate
readiness state the frontend can poll, so a user hitting a slow first
upload gets a clear "AI model is initializing" state instead of an
unexplained-looking wait.

Single backend process (no multi-worker uvicorn in this project), so a
plain module-level singleton is sufficient - no cross-process
synchronization needed.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal, Optional

EmbeddingReadinessStatus = Literal["not_started", "warming", "ready", "failed"]


@dataclass
class _State:
    status: EmbeddingReadinessStatus = "not_started"
    started_at: Optional[float] = None
    ready_at: Optional[float] = None
    error: Optional[str] = None


_state = _State()


def mark_warming() -> None:
    _state.status = "warming"
    _state.started_at = time.monotonic()
    _state.error = None


def mark_ready() -> None:
    _state.status = "ready"
    _state.ready_at = time.monotonic()
    _state.error = None


def mark_failed(reason: str) -> None:
    # `reason` must already be safe to expose (a class name or short fixed
    # string, never a raw exception message that could carry a path or
    # other environment detail) - callers are responsible for that, same
    # convention as the rest of this codebase's error handling.
    _state.status = "failed"
    _state.error = reason


def get_embedding_readiness() -> dict:
    elapsed_seconds = None
    if _state.started_at is not None:
        end = _state.ready_at if _state.ready_at is not None else time.monotonic()
        elapsed_seconds = round(end - _state.started_at, 1)
    return {
        "status": _state.status,
        "elapsed_seconds": elapsed_seconds,
        "error": _state.error,
    }


def _reset_for_tests() -> None:
    global _state
    _state = _State()
