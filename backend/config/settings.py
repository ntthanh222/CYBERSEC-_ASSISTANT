"""Application configuration loaded from environment variables."""
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.core.local_auth_secret import load_or_create_local_auth_secret
from backend.core.tls import apply_ssl_mode, require_secure_tls

_DEFAULT_SECRET_VALUES = {"", "change-me"}
_APP_ENVS = {"local", "test", "staging", "production"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: str = Field(default="development")

    # Phase 2.5A: explicit deployment-target axis, separate from the legacy
    # `environment` field above (which existing logging/seed-guard code keys
    # on and which this phase does not disturb). `app_env` is what decides
    # whether a Supabase (staging/production) or Docker (local/test) target
    # is expected, and whether TLS is required by default.
    app_env: str = Field(default="local")

    db_host: str = Field(default="postgres")
    db_port: int = Field(default=5432)
    db_name: str = Field(default="cybersec_assistant")
    db_user: str = Field(default="cybersec")
    db_password: str = Field(default="change-me")

    # Phase 2.5A: when set, these win over the discrete db_* fields above.
    # DATABASE_URL is for the running application (pooled, e.g. Supabase's
    # Session Pooler); DATABASE_MIGRATION_URL is for Alembic and
    # administrative scripts and may point at a direct (non-pooled)
    # connection. Neither is required locally - the db_* fields remain the
    # zero-config Docker Compose default.
    database_url_raw: str = Field(default="", validation_alias="DATABASE_URL")
    database_migration_url_raw: str = Field(default="", validation_alias="DATABASE_MIGRATION_URL")
    database_ssl_mode: str = Field(default="", validation_alias="DATABASE_SSL_MODE")

    # Reserved for future direct Supabase API/tooling use (e.g. the data
    # migration CLI's target validation). The application does not call the
    # Supabase client SDK in Phase 2.5A - all runtime access to Postgres goes
    # through SQLAlchemy via database_url. supabase_publishable_key is a
    # public/anon-scoped key by Supabase's own design; supabase_secret_key is
    # server-only and must never reach the frontend.
    supabase_url: str = Field(default="", validation_alias="SUPABASE_URL")
    supabase_publishable_key: str = Field(default="", validation_alias="SUPABASE_PUBLISHABLE_KEY")
    supabase_secret_key: str = Field(default="", validation_alias="SUPABASE_SECRET_KEY")

    # Phase 2.5B: Supabase Auth (GoTrue) JWT verification. The backend never
    # issues its own tokens - it only verifies what Supabase Auth signed.
    # Asymmetric (RS256/ES256) projects need none of these secrets: the
    # public key set is fetched from `supabase_jwks_url` and cached by kid.
    # `supabase_jwt_secret` exists ONLY for a project still on the legacy
    # symmetric (HS256) signing key and must be the dedicated JWT secret from
    # Supabase's Auth settings - never the anon/publishable or service-role
    # key, which are not valid JWT-verification secrets and would silently
    # accept forged tokens if used as one.
    supabase_jwt_secret: str = Field(default="", validation_alias="SUPABASE_JWT_SECRET")
    supabase_jwks_cache_seconds: int = Field(
        default=3600, validation_alias="SUPABASE_JWKS_CACHE_SECONDS"
    )

    # Docker-local-only demo auth (backend/api/local_auth.py). Points at a
    # file on the dedicated `local_auth_secret` named volume (see
    # docker-compose.yml) - see backend/core/local_auth_secret.py for the
    # generate-once/reuse-thereafter logic. Never a fixed value in source.
    local_auth_secret_path: str = Field(
        default="/app/.local-secret/jwt-secret", validation_alias="LOCAL_AUTH_SECRET_PATH"
    )

    # Set by `_default_local_auth_secret` below (never from env) to record
    # whether `supabase_jwt_secret` came from a real externally-supplied
    # value rather than the generated-and-persisted local file - so a
    # readiness check can tell "a real secret was intentionally supplied,
    # the file is correctly never written" apart from "the file failed to
    # persist". Read-only from the outside; not part of the public config
    # surface.
    local_auth_secret_externally_supplied: bool = False

    # Phase 2.6: RAG embeddings. The default provider is local - a model runs
    # in-process (fastembed/ONNX, no network call per document) and nothing in
    # a user's document is ever sent to an external service. A cloud provider
    # exists only as an explicit opt-in: it activates solely when both
    # EMBEDDING_PROVIDER=gemini *and* GEMINI_API_KEY are set, mirroring how
    # the chat LLM provider is selected (presence-of-key-implies-configured).
    # The vector column width in migration 0005 is fixed to
    # EMBEDDING_DIMENSION at migration-authoring time - changing this value
    # for an existing deployment requires a new migration that resizes the
    # column and re-embeds every stored chunk; it is not a hot-swappable
    # runtime setting.
    embedding_provider: str = Field(default="local", validation_alias="EMBEDDING_PROVIDER")
    embedding_model_name: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        validation_alias="EMBEDDING_MODEL_NAME",
    )
    embedding_dimension: int = Field(default=384, validation_alias="EMBEDDING_DIMENSION")
    embedding_cache_dir: str = Field(default="", validation_alias="EMBEDDING_CACHE_DIR")
    gemini_embedding_model: str = Field(
        default="text-embedding-004", validation_alias="GEMINI_EMBEDDING_MODEL"
    )

    # Phase 2.6: knowledge ingestion/retrieval tunables. All configurable so
    # limits can be tightened operationally without a code change; none is a
    # secret.
    rag_max_upload_bytes: int = Field(default=15_000_000, validation_alias="RAG_MAX_UPLOAD_BYTES")
    rag_max_pages: int = Field(default=300, validation_alias="RAG_MAX_PAGES")
    rag_max_chunks_per_document: int = Field(
        default=2000, validation_alias="RAG_MAX_CHUNKS_PER_DOCUMENT"
    )
    rag_chunk_size_chars: int = Field(default=1200, validation_alias="RAG_CHUNK_SIZE_CHARS")
    rag_chunk_overlap_chars: int = Field(default=200, validation_alias="RAG_CHUNK_OVERLAP_CHARS")
    rag_min_chunk_chars: int = Field(default=40, validation_alias="RAG_MIN_CHUNK_CHARS")
    rag_retrieval_top_k: int = Field(default=5, validation_alias="RAG_RETRIEVAL_TOP_K")
    # Measured, not guessed: the default local model (a general-purpose
    # sentence-similarity model, not one fine-tuned for asymmetric
    # query-to-passage retrieval) produces cosine similarities around
    # 0.2-0.6 for genuinely relevant query/passage pairs and near 0 or
    # negative for unrelated ones - see the calibration table in
    # docs/RAG_ARCHITECTURE.md. A 0.55 "sounds safe" threshold would silently
    # discard true matches with this model.
    rag_similarity_threshold: float = Field(
        default=0.20, validation_alias="RAG_SIMILARITY_THRESHOLD"
    )
    rag_max_context_chars: int = Field(default=6000, validation_alias="RAG_MAX_CONTEXT_CHARS")
    rag_allow_general_knowledge_fallback: bool = Field(
        default=True, validation_alias="RAG_ALLOW_GENERAL_KNOWLEDGE_FALLBACK"
    )
    # Hybrid retrieval (vector + full-text + exact-match) tunables. The
    # candidate pool is deliberately wider than what's ever sent to the LLM -
    # MMR/rerank need room to actually choose among alternatives.
    rag_candidate_pool_size: int = Field(default=20, validation_alias="RAG_CANDIDATE_POOL_SIZE")
    rag_mmr_lambda: float = Field(default=0.65, validation_alias="RAG_MMR_LAMBDA")
    rag_retrieval_cache_ttl_seconds: int = Field(
        default=600, validation_alias="RAG_RETRIEVAL_CACHE_TTL_SECONDS"
    )

    redis_host: str = Field(default="redis")
    redis_port: int = Field(default=6379)
    redis_url: str = Field(default="redis://redis:6379/0")

    jwt_secret: str = Field(default="change-me")
    secret_key: str = Field(default="change-me")

    cors_origins: str = Field(default="http://localhost:3000")

    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-2.5-flash")
    # Demo Mode: when true, the AI capability is only ever reported READY
    # after a real generateContent call has actually succeeded - a present
    # GEMINI_API_KEY alone (provider_configured=true) is not enough. See
    # backend/core/gemini_readiness.py and FINAL_MASTER_PROMPT_CYBERSEC_
    # ASSISTANT.md section C.6.
    demo_require_gemini: bool = Field(default=False, validation_alias="DEMO_REQUIRE_GEMINI")
    virustotal_api_key: str = Field(default="")
    nist_nvd_api_key: str = Field(default="")
    super_admin_ids: str = Field(default="")

    # Demo Mode account bootstrap (backend/services/demo_accounts.py). Only
    # ever runs when app_env == "local" - a hosted/staging/production
    # deployment must never gain accounts it didn't explicitly create.
    # Passwords are intentionally NOT defaulted to anything: an operator who
    # enables seeding without setting a password gets a clear startup log
    # explaining what's missing, never a silently-generated weak password.
    demo_seed_enabled: bool = Field(default=False, validation_alias="DEMO_SEED_ENABLED")
    demo_user_password: str = Field(default="", validation_alias="DEMO_USER_PASSWORD")
    demo_analyst_password: str = Field(default="", validation_alias="DEMO_ANALYST_PASSWORD")
    # demo_admin (role "admin") is retired - demo_superadmin is now the sole
    # privileged demo account, carrying every admin capability plus
    # super_admin-only ones. See backend/services/demo_accounts.py.
    demo_superadmin_password: str = Field(default="", validation_alias="DEMO_SUPERADMIN_PASSWORD")

    # Anonymous, zero-credential "Local Mode" session (POST /api/auth/local-session -
    # backend/api/local_auth.py::start_local_session). Distinct from the
    # credentialed demo-account sign-in (/api/auth/local-login), which stays
    # available whenever DEMO_SEED_ENABLED=true so the seeded demo accounts can
    # actually log in. `None` (unset) means "operator hasn't overridden it":
    # default to allowed for plain local dev, but default to DISALLOWED the
    # moment Demo Mode is active, since an anonymous no-password session would
    # otherwise be reachable side-by-side with the demo accounts it's meant to
    # be replaced by. An explicit ALLOW_LOCAL_MODE always wins either way.
    allow_local_mode_override: Optional[bool] = Field(
        default=None, validation_alias="ALLOW_LOCAL_MODE"
    )

    # Phase 2 tunables. Defaults are chosen so the whole toolkit works with an
    # empty .env; none of them is a secret.
    cve_cache_ttl_seconds: int = Field(default=3600)
    url_scan_timeout_seconds: float = Field(default=8.0)
    url_scan_max_redirects: int = Field(default=5)
    url_scan_max_response_bytes: int = Field(default=512_000)

    # Task 6 (CVE Risk Prioritization): EPSS and CISA KEV are both public,
    # keyless feeds (verified against their published documentation - see
    # backend/providers/enrichment/epss.py and kev.py's module docstrings)
    # so unlike nist_nvd_api_key above, there is no API-key field to add
    # here. Base URLs are still configurable (same rationale as
    # NvdProvider.DEFAULT_BASE_URL being overridable) in case an operator
    # needs to point at a mirror/proxy. EPSS reuses cve_cache_ttl_seconds'
    # order of magnitude (per-CVE data, refreshed roughly as often as CVSS
    # data is). KEV gets its own, much longer TTL: it is a whole-catalog
    # download, not a per-CVE call, and CISA updates it infrequently (at
    # most a few times a week), so caching it for hours rather than the
    # ~1 hour CVE/EPSS TTL avoids re-downloading a multi-hundred-KB feed
    # on every assessment without going stale in any way that matters for
    # prioritization purposes.
    epss_base_url: str = Field(
        default="https://api.first.org/data/v1/epss", validation_alias="EPSS_BASE_URL"
    )
    epss_cache_ttl_seconds: int = Field(default=3600, validation_alias="EPSS_CACHE_TTL_SECONDS")
    kev_feed_url: str = Field(
        default="https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
        validation_alias="KEV_FEED_URL",
    )
    kev_cache_ttl_seconds: int = Field(default=21_600, validation_alias="KEV_CACHE_TTL_SECONDS")

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def database_url(self) -> str:
        """Runtime application DSN: DATABASE_URL if set, else the local Docker default."""
        base = self.database_url_raw or (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )
        return apply_ssl_mode(base, self.database_ssl_mode)

    @property
    def database_migration_url(self) -> str:
        """Alembic/administrative DSN: DATABASE_MIGRATION_URL if set, else database_url."""
        if self.database_migration_url_raw:
            return apply_ssl_mode(self.database_migration_url_raw, self.database_ssl_mode)
        return self.database_url

    @property
    def sync_database_url(self) -> str:
        """Alias kept for existing callers (Alembic, seed/reset scripts)."""
        return self.database_migration_url

    @property
    def supabase_issuer(self) -> str:
        """Expected `iss` claim on every Supabase Auth token."""
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def embedding_cloud_configured(self) -> bool:
        """Whether the optional cloud embedding provider is actually active.

        Requires an *explicit* opt-in (``EMBEDDING_PROVIDER=gemini``) in
        addition to a configured key - setting the key alone never switches a
        deployment away from the local, free-by-default path.
        """
        return self.embedding_provider.lower() == "gemini" and bool(self.gemini_api_key)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production" or self.app_env.lower() == "production"

    @property
    def is_local(self) -> bool:
        return self.app_env.lower() == "local"

    @property
    def allow_local_mode(self) -> bool:
        """Whether the anonymous, zero-credential Local Mode session
        (`POST /api/auth/local-session`) may be used. See the field doc on
        `allow_local_mode_override` for the default-flip-under-Demo-Mode logic."""
        if self.allow_local_mode_override is not None:
            return self.allow_local_mode_override
        return not (self.demo_seed_enabled or self.demo_require_gemini)

    @property
    def requires_supabase_target(self) -> bool:
        """True for staging/production, where a Docker-default DSN would be a real mistake."""
        return self.app_env.lower() in {"staging", "production"}

    @model_validator(mode="after")
    def _reject_default_secrets_in_production(self) -> "Settings":
        if self.is_production:
            unsafe = (
                self.jwt_secret in _DEFAULT_SECRET_VALUES
                or self.secret_key in _DEFAULT_SECRET_VALUES
                or self.db_password in _DEFAULT_SECRET_VALUES
            )
            if unsafe:
                raise ValueError(
                    "Refusing to start with ENVIRONMENT=production while JWT_SECRET, "
                    "SECRET_KEY or DB_PASSWORD still hold default/empty values."
                )
        return self

    @model_validator(mode="after")
    def _validate_app_env(self) -> "Settings":
        if self.app_env.lower() not in _APP_ENVS:
            raise ValueError(
                f"APP_ENV must be one of {sorted(_APP_ENVS)}, got {self.app_env!r}."
            )
        return self

    @model_validator(mode="after")
    def _default_local_auth_secret(self) -> "Settings":
        # Docker-local zero-config convenience only: fills the legacy-HS256
        # verification secret with a persistent, runtime-generated random
        # value (backend/core/local_auth_secret.py) so the local-only
        # demo-session endpoint works out of the box, survives restarts, and
        # is never a fixed value anyone could guess from source. Only
        # applies when app_env == "local" AND no real secret was already
        # supplied - a real SUPABASE_JWT_SECRET always wins. Never applies
        # in staging/production regardless of this field's value.
        self.local_auth_secret_externally_supplied = self.is_local and bool(
            self.supabase_jwt_secret
        )
        if self.is_local and not self.supabase_jwt_secret:
            self.supabase_jwt_secret = load_or_create_local_auth_secret(self.local_auth_secret_path)
        return self

    @model_validator(mode="after")
    def _require_explicit_target_for_staging_and_production(self) -> "Settings":
        # A staging/production process silently falling back to the Docker
        # default DSN (postgres:5432, local-only credentials) would connect
        # to nothing reachable and fail loudly - but it could just as easily
        # mean someone forgot to set DATABASE_URL and the process quietly
        # points at whatever "postgres" resolves to in that environment.
        # Require the operator to say so explicitly.
        if self.requires_supabase_target and not self.database_url_raw:
            raise ValueError(
                "APP_ENV=staging|production requires DATABASE_URL to be set explicitly "
                "(no fallback to the local Docker default DSN)."
            )
        return self

    @model_validator(mode="after")
    def _validate_embedding_provider(self) -> "Settings":
        allowed = {"local", "gemini"}
        if self.embedding_provider.lower() not in allowed:
            raise ValueError(
                f"EMBEDDING_PROVIDER must be one of {sorted(allowed)}, "
                f"got {self.embedding_provider!r}."
            )
        if self.embedding_dimension <= 0:
            raise ValueError("EMBEDDING_DIMENSION must be a positive integer.")
        return self

    @model_validator(mode="after")
    def _require_tls_for_staging_and_production(self) -> "Settings":
        # Runs after the validator above, so database_url_raw is already
        # known to be set whenever this matters. Checks both DSNs
        # unconditionally - which one the process actually uses at runtime
        # is irrelevant, both must be safe (see backend/core/tls.py).
        require_secure_tls(
            url=self.database_url,
            database_ssl_mode=self.database_ssl_mode,
            app_env=self.app_env,
            label="DATABASE_URL",
        )
        require_secure_tls(
            url=self.database_migration_url,
            database_ssl_mode=self.database_ssl_mode,
            app_env=self.app_env,
            label="DATABASE_MIGRATION_URL",
        )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
