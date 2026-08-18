"""Unit tests for Supabase Auth JWT verification (backend.core.auth).

An in-process RSA keypair stands in for Supabase's own signing key; the
JWKS HTTP fetch is monkeypatched so these tests never touch the network.
Every rejection path must raise :class:`AuthenticationError` (mapped to a
generic 401) - the whole point being that a caller can never tell which
check failed.
"""
import time
import uuid

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.config.settings import Settings
from backend.core import auth as auth_module
from backend.core.auth import (
    AuthenticatedUser,
    EXPECTED_AUDIENCE,
    _extract_bearer_token,
    verify_access_token,
)
from backend.core.exceptions import AuthenticationError

SUPABASE_URL = "https://project-ref.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"
KID = "test-key-1"


@pytest.fixture()
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture(autouse=True)
def _reset_jwks_cache():
    auth_module._reset_jwks_cache_for_tests()
    yield
    auth_module._reset_jwks_cache_for_tests()


def _settings(**overrides) -> Settings:
    base = {
        "SUPABASE_URL": SUPABASE_URL,
        "APP_ENV": "staging",
        "DATABASE_URL": "postgresql+psycopg://user:pass@host:5432/db?sslmode=require",
        "DATABASE_SSL_MODE": "require",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


def _jwks_document(public_key, *, kid: str = KID) -> dict:
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(public_key, as_dict=True)
    jwk["kid"] = kid
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return {"keys": [jwk]}


def _patch_jwks(monkeypatch, document: dict) -> None:
    async def fake_get(self, url, *args, **kwargs):
        request = httpx.Request("GET", url)
        return httpx.Response(200, json=document, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)


def _token(private_key, *, kid=KID, alg="RS256", **claim_overrides) -> str:
    now = int(time.time())
    claims = {
        "sub": str(uuid.uuid4()),
        "aud": EXPECTED_AUDIENCE,
        "iss": ISSUER,
        "role": "authenticated",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(claim_overrides)
    return jwt.encode(claims, private_key, algorithm=alg, headers={"kid": kid})


class TestExtractBearerToken:
    def test_missing_header_raises(self):
        class FakeRequest:
            headers = {}

        with pytest.raises(AuthenticationError):
            _extract_bearer_token(FakeRequest())

    def test_wrong_scheme_raises(self):
        class FakeRequest:
            headers = {"authorization": "Basic abc123"}

        with pytest.raises(AuthenticationError):
            _extract_bearer_token(FakeRequest())

    def test_valid_bearer_extracts_token(self):
        class FakeRequest:
            headers = {"authorization": "Bearer my-token"}

        assert _extract_bearer_token(FakeRequest()) == "my-token"


class TestVerifyAccessTokenAsymmetric:
    @pytest.mark.asyncio
    async def test_valid_token_verifies(self, rsa_keypair, monkeypatch):
        private_key, public_key = rsa_keypair
        _patch_jwks(monkeypatch, _jwks_document(public_key))
        settings = _settings()
        token = _token(private_key)

        user = await verify_access_token(token, settings=settings)

        assert isinstance(user, AuthenticatedUser)
        assert user.role == "authenticated"
        assert str(user.id) == jwt.decode(token, options={"verify_signature": False})["sub"]

    @pytest.mark.asyncio
    async def test_unknown_kid_rejected(self, rsa_keypair, monkeypatch):
        private_key, public_key = rsa_keypair
        _patch_jwks(monkeypatch, _jwks_document(public_key, kid="the-real-kid"))
        settings = _settings()
        token = _token(private_key, kid="not-the-real-kid")

        with pytest.raises(AuthenticationError):
            await verify_access_token(token, settings=settings)

    @pytest.mark.asyncio
    async def test_kid_rotation_triggers_one_refresh(self, rsa_keypair, monkeypatch):
        """A kid absent from the cached JWKS forces exactly one refetch."""
        private_key, public_key = rsa_keypair
        calls = {"count": 0}
        document = _jwks_document(public_key, kid="rotated-kid")

        async def fake_get(self, url, *args, **kwargs):
            calls["count"] += 1
            request = httpx.Request("GET", url)
            return httpx.Response(200, json=document, request=request)

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        settings = _settings()
        token = _token(private_key, kid="rotated-kid")

        user = await verify_access_token(token, settings=settings)

        assert isinstance(user, AuthenticatedUser)
        assert calls["count"] == 1  # cache was empty, one fetch found the key immediately

    @pytest.mark.asyncio
    async def test_wrong_signature_rejected(self, rsa_keypair, monkeypatch):
        private_key, public_key = rsa_keypair
        other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        _patch_jwks(monkeypatch, _jwks_document(public_key))
        settings = _settings()
        # Signed by a different key than the one published in JWKS.
        token = _token(other_private_key)

        with pytest.raises(AuthenticationError):
            await verify_access_token(token, settings=settings)

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, rsa_keypair, monkeypatch):
        private_key, public_key = rsa_keypair
        _patch_jwks(monkeypatch, _jwks_document(public_key))
        settings = _settings()
        token = _token(private_key, exp=int(time.time()) - 60)

        with pytest.raises(AuthenticationError):
            await verify_access_token(token, settings=settings)

    @pytest.mark.asyncio
    async def test_wrong_issuer_rejected(self, rsa_keypair, monkeypatch):
        private_key, public_key = rsa_keypair
        _patch_jwks(monkeypatch, _jwks_document(public_key))
        settings = _settings()
        token = _token(private_key, iss="https://not-your-project.supabase.co/auth/v1")

        with pytest.raises(AuthenticationError):
            await verify_access_token(token, settings=settings)

    @pytest.mark.asyncio
    async def test_wrong_audience_rejected(self, rsa_keypair, monkeypatch):
        private_key, public_key = rsa_keypair
        _patch_jwks(monkeypatch, _jwks_document(public_key))
        settings = _settings()
        token = _token(private_key, aud="not-authenticated")

        with pytest.raises(AuthenticationError):
            await verify_access_token(token, settings=settings)

    @pytest.mark.asyncio
    async def test_missing_sub_rejected(self, rsa_keypair, monkeypatch):
        private_key, public_key = rsa_keypair
        _patch_jwks(monkeypatch, _jwks_document(public_key))
        settings = _settings()
        now = int(time.time())
        claims = {
            "aud": EXPECTED_AUDIENCE,
            "iss": ISSUER,
            "iat": now,
            "exp": now + 3600,
        }
        token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": KID})

        with pytest.raises(AuthenticationError):
            await verify_access_token(token, settings=settings)

    @pytest.mark.asyncio
    async def test_non_uuid_sub_rejected(self, rsa_keypair, monkeypatch):
        private_key, public_key = rsa_keypair
        _patch_jwks(monkeypatch, _jwks_document(public_key))
        settings = _settings()
        token = _token(private_key, sub="not-a-uuid")

        with pytest.raises(AuthenticationError):
            await verify_access_token(token, settings=settings)

    @pytest.mark.asyncio
    async def test_malformed_token_rejected(self, settings=None):
        settings = _settings()
        with pytest.raises(AuthenticationError):
            await verify_access_token("not-a-jwt-at-all", settings=settings)

    @pytest.mark.asyncio
    async def test_jwks_fetch_failure_rejected(self, monkeypatch):
        async def fake_get(self, url, *args, **kwargs):
            raise httpx.ConnectError("connection refused", request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        settings = _settings()
        # Any RS256-shaped token triggers a JWKS fetch before signature
        # verification can even be attempted.
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = _token(private_key)

        with pytest.raises(AuthenticationError):
            await verify_access_token(token, settings=settings)

    @pytest.mark.asyncio
    async def test_unsupported_algorithm_rejected(self, rsa_keypair, monkeypatch):
        private_key, public_key = rsa_keypair
        _patch_jwks(monkeypatch, _jwks_document(public_key))
        settings = _settings()
        # "none" algorithm - the classic unsigned-token forgery attempt.
        now = int(time.time())
        claims = {
            "sub": str(uuid.uuid4()),
            "aud": EXPECTED_AUDIENCE,
            "iss": ISSUER,
            "iat": now,
            "exp": now + 3600,
        }
        forged = jwt.encode(claims, key=None, algorithm="none", headers={"kid": KID})

        with pytest.raises(AuthenticationError):
            await verify_access_token(forged, settings=settings)


class TestVerifyAccessTokenLegacyHs256:
    @pytest.mark.asyncio
    async def test_valid_hs256_token_with_secret_configured(self):
        secret = "a-real-legacy-jwt-secret-from-supabase-auth-settings"
        settings = _settings(SUPABASE_JWT_SECRET=secret)
        now = int(time.time())
        claims = {
            "sub": str(uuid.uuid4()),
            "aud": EXPECTED_AUDIENCE,
            "iss": ISSUER,
            "role": "authenticated",
            "iat": now,
            "exp": now + 3600,
        }
        token = jwt.encode(claims, secret, algorithm="HS256")

        user = await verify_access_token(token, settings=settings)
        assert isinstance(user, AuthenticatedUser)

    @pytest.mark.asyncio
    async def test_hs256_rejected_when_secret_not_configured(self):
        settings = _settings(SUPABASE_JWT_SECRET="")
        now = int(time.time())
        claims = {
            "sub": str(uuid.uuid4()),
            "aud": EXPECTED_AUDIENCE,
            "iss": ISSUER,
            "iat": now,
            "exp": now + 3600,
        }
        # Signed with some arbitrary value - it must never be accepted
        # regardless, since no secret is configured to check it against.
        token = jwt.encode(claims, "whatever-someone-guessed", algorithm="HS256")

        with pytest.raises(AuthenticationError):
            await verify_access_token(token, settings=settings)

    @pytest.mark.asyncio
    async def test_hs256_never_verified_with_publishable_or_service_role_key(self):
        """The anon/service-role keys must never work as an HS256 secret."""
        settings = _settings(
            SUPABASE_JWT_SECRET="",
            SUPABASE_PUBLISHABLE_KEY="sb_publishable_not_a_jwt_secret",
            SUPABASE_SECRET_KEY="sb_secret_not_a_jwt_secret_either",
        )
        now = int(time.time())
        claims = {
            "sub": str(uuid.uuid4()),
            "aud": EXPECTED_AUDIENCE,
            "iss": ISSUER,
            "iat": now,
            "exp": now + 3600,
        }
        forged = jwt.encode(claims, "sb_publishable_not_a_jwt_secret", algorithm="HS256")

        with pytest.raises(AuthenticationError):
            await verify_access_token(forged, settings=settings)
