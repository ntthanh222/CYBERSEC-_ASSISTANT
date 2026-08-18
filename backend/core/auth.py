"""Supabase Auth (GoTrue) JWT verification.

The backend never issues, signs, or stores its own tokens and never runs a
password system of its own - it only verifies what Supabase Auth already
signed. Two signing modes exist across Supabase projects:

* **Asymmetric (RS256/ES256)** - the default for new projects. The public
  key set is fetched from ``<SUPABASE_URL>/auth/v1/.well-known/jwks.json``
  and cached by ``kid``; nothing secret is ever held by this process.
* **Legacy symmetric (HS256)** - older projects still on the shared JWT
  secret. Verification needs ``SUPABASE_JWT_SECRET`` (the dedicated JWT
  secret from Supabase's Auth settings - *not* the anon/publishable key and
  *not* the service-role key, neither of which is a valid HMAC verification
  secret). If that variable is unset, HS256 tokens are rejected outright
  rather than guessed at.

Every failure mode - missing header, bad signature, expired, wrong
issuer/audience, unknown/unrefreshable ``kid``, unset legacy secret -
collapses to the same generic 401 (:class:`backend.core.exceptions.AuthenticationError`).
The response must never tell a caller which check failed.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
import jwt
from fastapi import Request
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

from backend.config.settings import Settings, get_settings
from backend.core.exceptions import AuthenticationError

logger = logging.getLogger("backend.auth")

_ASYMMETRIC_ALGS = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"})
_SYMMETRIC_ALGS = frozenset({"HS256", "HS384", "HS512"})
_SUPPORTED_ALGS = _ASYMMETRIC_ALGS | _SYMMETRIC_ALGS

#: Supabase Auth issues tokens with this audience by default.
EXPECTED_AUDIENCE = "authenticated"


@dataclass(frozen=True)
class AuthenticatedUser:
    """The verified identity of the caller, derived only from the token.

    ``id`` is the Postgres/Supabase user UUID from the ``sub`` claim - the
    single source of truth for ownership everywhere in this codebase. It is
    never accepted from a request body, query string, or custom header.
    """

    id: uuid.UUID
    role: str
    claims: dict[str, Any] = field(default_factory=dict)


class _JwksCache:
    """Fetches and caches a Supabase project's JWKS, keyed by ``kid``.

    A cache miss on a known ``kid`` triggers exactly one forced refresh (to
    tolerate Supabase rotating signing keys) before the token is rejected -
    never an unbounded retry loop.
    """

    def __init__(self) -> None:
        self._keys: dict[str, Any] = {}
        self._fetched_at: float = 0.0
        self._jwks_url: Optional[str] = None

    def _is_fresh(self, ttl_seconds: int) -> bool:
        return bool(self._keys) and (time.monotonic() - self._fetched_at) < ttl_seconds

    async def get_key(self, *, kid: str, jwks_url: str, ttl_seconds: int) -> Any:
        if self._jwks_url != jwks_url:
            # Pointed at a different project (or first use) - drop any stale cache.
            self._keys = {}
            self._fetched_at = 0.0
            self._jwks_url = jwks_url

        if kid not in self._keys or not self._is_fresh(ttl_seconds):
            await self._refresh(jwks_url)

        key = self._keys.get(kid)
        if key is None:
            # One forced refresh in case the key rotated since our last fetch.
            await self._refresh(jwks_url)
            key = self._keys.get(kid)
        if key is None:
            raise AuthenticationError()
        return key

    async def _refresh(self, jwks_url: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(jwks_url)
                response.raise_for_status()
                document = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("supabase_jwks_fetch_failed", extra={"fields": {"url": jwks_url}})
            raise AuthenticationError() from exc

        keys: dict[str, Any] = {}
        for jwk in document.get("keys", []):
            kid = jwk.get("kid")
            kty = jwk.get("kty")
            if not kid or not kty:
                continue
            try:
                if kty == "RSA":
                    keys[kid] = RSAAlgorithm.from_jwk(jwk)
                elif kty == "EC":
                    keys[kid] = ECAlgorithm.from_jwk(jwk)
                # Other key types are not signing algorithms Supabase Auth
                # uses for access tokens; silently skipped rather than
                # raising, so one unrelated key in the set cannot break
                # verification of every other key.
            except (ValueError, TypeError):
                logger.warning(
                    "supabase_jwks_key_unparseable", extra={"fields": {"kid": kid, "kty": kty}}
                )
        self._keys = keys
        self._fetched_at = time.monotonic()


_jwks_cache = _JwksCache()


def _reset_jwks_cache_for_tests() -> None:
    """Test-only helper: clear the process-wide JWKS cache between cases."""
    global _jwks_cache
    _jwks_cache = _JwksCache()


async def verify_access_token(
    token: str, *, settings: Optional[Settings] = None
) -> AuthenticatedUser:
    """Verify a Supabase Auth access token and return its identity.

    Raises :class:`AuthenticationError` (mapped to HTTP 401) for every
    failure - malformed token, unsupported/mismatched algorithm, unknown
    kid, expired, wrong issuer/audience, or a legacy HS256 project with no
    ``SUPABASE_JWT_SECRET`` configured.
    """
    settings = settings or get_settings()

    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError() from exc

    alg = header.get("alg")
    if alg not in _SUPPORTED_ALGS:
        raise AuthenticationError()

    verify_kwargs: dict[str, Any] = {
        "algorithms": [alg],
        "audience": EXPECTED_AUDIENCE,
        "issuer": settings.supabase_issuer,
        "options": {"require": ["exp", "iat", "sub", "aud", "iss"]},
    }

    if alg in _ASYMMETRIC_ALGS:
        kid = header.get("kid")
        if not kid:
            raise AuthenticationError()
        key = await _jwks_cache.get_key(
            kid=kid,
            jwks_url=settings.supabase_jwks_url,
            ttl_seconds=settings.supabase_jwks_cache_seconds,
        )
    else:
        # Legacy symmetric project. Never fall back to the anon/publishable
        # or service-role key - those are not JWT-verification secrets and
        # using either here would let a token signed with a public value be
        # accepted as genuine.
        if not settings.supabase_jwt_secret:
            logger.error(
                "supabase_legacy_hs256_secret_missing",
                extra={
                    "fields": {
                        "hint": "set SUPABASE_JWT_SECRET or migrate to asymmetric signing keys"
                    }
                },
            )
            raise AuthenticationError()
        key = settings.supabase_jwt_secret

    try:
        claims = jwt.decode(token, key=key, **verify_kwargs)
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError() from exc

    sub = claims.get("sub")
    try:
        user_id = uuid.UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise AuthenticationError() from exc

    role = claims.get("role") or EXPECTED_AUDIENCE
    return AuthenticatedUser(id=user_id, role=role, claims=claims)


def _extract_bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationError()
    return token


async def get_current_user(request: Request) -> AuthenticatedUser:
    """FastAPI dependency: the caller's verified identity, or a 401.

    This is the only place a `user_id` may come from anywhere in the
    application - never a request body field, query parameter, or custom
    header (those are all client-supplied and trivially forged).
    """
    token = _extract_bearer_token(request)
    return await verify_access_token(token)
