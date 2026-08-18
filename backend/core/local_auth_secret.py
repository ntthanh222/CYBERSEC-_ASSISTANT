"""Persistent, runtime-generated signing secret for Docker-local demo auth.

Never a fixed value in source, never baked into the image, never sent to
the frontend. The first backend process to start with an empty secret
file generates a cryptographically random one and writes it; every process
after that (including across `docker compose restart` and a full Docker
Desktop restart) reads the same file back, so existing Local Mode sessions
keep working. The file lives on a dedicated named Docker volume
(`local_auth_secret`, see docker-compose.yml) that only the backend
container can read - nothing else ever sees it, and it is never logged.
"""
from __future__ import annotations

import logging
import os
import secrets
import stat
from pathlib import Path

logger = logging.getLogger("backend.core.local_auth_secret")


def load_or_create_local_auth_secret(path: str) -> str:
    """Returns the persisted secret at `path`, generating one if absent.

    Falls back to an in-memory-only random secret (never written to disk)
    if the path can't be read or written - e.g. when running outside
    Docker (a plain `pytest` process with no volume mounted) where
    persistence isn't meaningful anyway. Either way the returned value is
    always genuinely random, never a fixed constant - the failure mode
    here is "generate a new one every process start", not "fall back to a
    guessable value".
    """
    try:
        secret_path = Path(path)
        if secret_path.exists():
            existing = secret_path.read_text(encoding="utf-8").strip()
            if existing:
                return existing
            # Empty file (e.g. a prior write was interrupted) - regenerate.
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        new_secret = secrets.token_urlsafe(48)
        secret_path.write_text(new_secret, encoding="utf-8")
        try:
            os.chmod(secret_path, stat.S_IRUSR | stat.S_IWUSR)  # 0600: owner read/write only
        except OSError:
            pass  # Best-effort on platforms/filesystems that don't support chmod bits.
        return new_secret
    except OSError as exc:
        logger.warning(
            "local_auth_secret_persistence_unavailable",
            extra={"fields": {"path": path, "error": type(exc).__name__}},
        )
        return secrets.token_urlsafe(48)
