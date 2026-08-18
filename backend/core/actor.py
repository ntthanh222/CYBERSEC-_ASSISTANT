"""Actor abstraction: "who is making this request?" for audit events,
scan-history rows and rate-limit buckets.

Real authentication (Phase 2.5B) has landed - a valid ``Authorization:
Bearer`` token's verified ``sub`` claim is always preferred when present, so
per-user rate-limit buckets and audit trails are actually scoped per user
instead of collapsing every caller into one shared bucket. Routes that don't
require login (URL scanner, password checker, ...) still fall back to the
optional, caller-supplied ``X-Actor`` header and then ``anonymous`` - that
fallback path remains **not a security control**, the header is trivially
forged, and is documented as UNPROTECTED in ``docs/SECURITY.md`` and the API
contract. It only ever applies when no valid token was presented.
"""
import re

from fastapi import Request

from backend.core.auth import _extract_bearer_token, verify_access_token
from backend.core.exceptions import AuthenticationError

ANONYMOUS_ACTOR = "anonymous"

# Same shape as the request-id allowlist in the request-context middleware:
# printable, bounded, and free of CR/LF so an actor value can never inject a
# line break into a log record or a response header.
_VALID_ACTOR = re.compile(r"^[A-Za-z0-9_.@-]{1,128}$")


def resolve_actor(raw: str | None) -> str:
    if raw and _VALID_ACTOR.match(raw):
        return raw
    return ANONYMOUS_ACTOR


async def get_current_actor(request: Request) -> str:
    """FastAPI dependency returning the request's actor identifier.

    Tries the real authenticated user first (same verification
    `get_current_user` uses - FastAPI's per-request dependency cache means
    this costs nothing extra on routes that already depend on
    `get_current_user`). Never raises: an absent, expired or malformed
    token just falls through to the header/anonymous path below, since this
    dependency is also used on routes that allow anonymous callers.
    """
    try:
        token = _extract_bearer_token(request)
        user = await verify_access_token(token)
        return str(user.id)
    except AuthenticationError:
        return resolve_actor(request.headers.get("x-actor"))
