"""FastAPI application entrypoint for Phase 1 (skeleton + health)."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from backend.api.admin import router as admin_router
from backend.api.alerts import router as alerts_router
from backend.api.attack_graph import router as attack_graph_router
from backend.api.assets import router as assets_router
from backend.api.chatbot import router as chatbot_router
from backend.api.cves import router as cves_router
from backend.api.demo import router as demo_router
from backend.api.health import router as health_router
from backend.api.incidents import router as incidents_router
from backend.api.knowledge import router as knowledge_router
from backend.api.local_admin import router as local_admin_router
from backend.api.local_admin import unified_login_router
from backend.api.local_auth import router as local_auth_router
from backend.api.metrics import router as metrics_router
from backend.api.mitre import router as mitre_router
from backend.api.notifications import router as notifications_router
from backend.api.projects import router as projects_router
from backend.api.reports import router as reports_router
from backend.api.scan_history import router as scan_history_router
from backend.api.security_news import router as security_news_router
from backend.api.system import router as system_router
from backend.api.threat_intel import router as threat_intel_router
from backend.api.tools import router as tools_router
from backend.api.vulnerabilities import router as vulnerabilities_router
from backend.api.workspaces import router as workspaces_router
from backend.config.settings import get_settings
from backend.core.context import get_request_id
from backend.core.embedding_readiness import mark_failed, mark_ready, mark_warming
from backend.core.exceptions import AppError
from backend.core.logging import configure_logging
from backend.core.metrics import observe_error, set_app_info
from backend.core.redis_client import close_redis
from backend.database.session import get_engine, get_sessionmaker
from backend.middleware.request_context import RequestContextMiddleware
from backend.middleware.security_headers import SecurityHeadersMiddleware
from backend.providers.embeddings.registry import get_embedding_provider
from backend.services.assistant import verify_gemini_readiness
from backend.services.demo_accounts import seed_demo_accounts
from backend.services.demo_knowledge import seed_demo_knowledge
from backend.services.demo_security_data import seed_demo_security_chain

API_VERSION = "0.3.0"

configure_logging()
settings = get_settings()
set_app_info(version=API_VERSION, environment=settings.environment)

logger = logging.getLogger("backend.main")


async def _warmup_embedding_model() -> None:
    """Loads the embedding model once, in the background, right after
    startup - never blocking app startup or the healthcheck. A failure here
    doesn't crash the app: the first real upload/chat request will just
    retry the load itself (and its own error path already handles a load
    failure), so this is a pure latency optimization, not a dependency.
    """
    mark_warming()
    try:
        provider = get_embedding_provider()
        await provider.embed(["warmup"])
        mark_ready()
    except Exception as exc:  # noqa: BLE001 - background task must never raise
        logger.warning("embedding_warmup_failed", extra={"fields": {"error": type(exc).__name__}})
        mark_failed(type(exc).__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Never in the unit-test environment: conftest.py's TestClient fixtures
    # start/stop the app once per test, and a real ONNX model load per test
    # would make the suite unusably slow (and require the real dependency
    # to be present) for zero benefit - no test exercises real cold-start
    # UX. `environment == "test"` uniquely identifies that case (set by
    # conftest.py; app_env stays "local" even in tests, so it can't be
    # used for this distinction).
    warmup_task = None
    gemini_check_task = None
    if settings.environment.lower() != "test":
        warmup_task = asyncio.create_task(_warmup_embedding_model())
        # Fire-and-forget, same posture as the embedding warmup: a slow or
        # failed Gemini probe must never delay startup or the healthcheck.
        # Only runs at all when DEMO_REQUIRE_GEMINI=true and a key is
        # configured - see verify_gemini_readiness's own docstring for why
        # this is a one-shot startup probe, not per-request.
        if settings.demo_require_gemini and settings.gemini_api_key:
            gemini_check_task = asyncio.create_task(verify_gemini_readiness())

    # Awaited, not fire-and-forget: unlike the embedding warmup above (a
    # pure latency optimization), Playwright/acceptance flows may try to log
    # in as a demo account within seconds of the healthcheck passing, so the
    # accounts must actually exist before startup completes. Never raises
    # (see seed_demo_accounts's own docstring) and is a no-op unless both
    # APP_ENV=local and DEMO_SEED_ENABLED=true.
    if settings.environment.lower() != "test":
        async with get_sessionmaker()() as seed_session:
            await seed_demo_accounts(seed_session, settings=settings)
        async with get_sessionmaker()() as seed_session:
            await seed_demo_knowledge(seed_session, settings=settings)
        # Must run after seed_demo_accounts (needs demo_superadmin to
        # already exist) - never raises, no-op unless both APP_ENV=local and
        # DEMO_SEED_ENABLED=true, same posture as the two seeds above.
        async with get_sessionmaker()() as seed_session:
            await seed_demo_security_chain(seed_session, settings=settings)

    yield
    if warmup_task is not None:
        warmup_task.cancel()
    if gemini_check_task is not None:
        gemini_check_task.cancel()
    await get_engine().dispose()
    await close_redis()


_docs_enabled = settings.app_env.lower() not in {"staging", "production"}

app = FastAPI(
    title="CyberSec Assistant API",
    version=API_VERSION,
    description=(
        "API for the CyberSec Assistant rebuild.\n\n"
        "**Phase 1/1.5** provides liveness, aggregated dependency health and "
        "Prometheus metrics. **Phase 2** adds the AI Security Assistant and the "
        "Security Toolkit (URL Scanner, Password Checker, CVE Lookup, Scan "
        "History). **Phase 2.5B** adds Supabase Auth: every `chatbot`, "
        "`tools`, `cves` and `knowledge` route requires `Authorization: "
        "Bearer <supabase-access-token>` and returns 401 without one. "
        "**Phase 2.6** adds Retrieval-Augmented Generation: a `knowledge` "
        "base of uploaded documents, embedded with pgvector, retrieved with "
        "Row Level Security enforced, and cited in `/api/chatbot/chat` "
        "answers. See `docs/SECURITY.md` and `docs/RAG_ARCHITECTURE.md`."
    ),
    lifespan=lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
    openapi_tags=[
        {"name": "health", "description": "Lightweight liveness probe for orchestrators."},
        {"name": "system", "description": "Real, aggregated dependency health for humans/UI."},
        {"name": "metrics", "description": "Prometheus scrape endpoint."},
        {
            "name": "chatbot",
            "description": (
                "AI Security Assistant: conversations, messages and chat. The "
                "reported provider always names what actually answered."
            ),
        },
        {
            "name": "tools",
            "description": (
                "Security Toolkit: URL scanning with SSRF protection, stateless "
                "password strength analysis, and scan history."
            ),
        },
        {
            "name": "cves",
            "description": "CVE lookup and search backed by the public NVD API with Redis caching.",
        },
        {
            "name": "knowledge",
            "description": (
                "Phase 2.6 Retrieval-Augmented Generation: document upload, "
                "chunking, embeddings, and retrieval preview. The chatbot's "
                "`/api/chatbot/chat` uses the same retrieval to ground answers "
                "with citations."
            ),
        },
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID", "X-Correlation-ID"],
    expose_headers=["X-Request-ID", "X-Correlation-ID"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)

app.include_router(health_router)
app.include_router(system_router)
app.include_router(metrics_router)
app.include_router(chatbot_router)
app.include_router(tools_router)
app.include_router(scan_history_router)
app.include_router(cves_router)
app.include_router(demo_router)
app.include_router(knowledge_router)
app.include_router(local_auth_router)
app.include_router(local_admin_router)
app.include_router(unified_login_router)
app.include_router(admin_router)
app.include_router(assets_router)
app.include_router(threat_intel_router)
app.include_router(vulnerabilities_router)
app.include_router(alerts_router)
app.include_router(incidents_router)
app.include_router(mitre_router)
app.include_router(attack_graph_router)
app.include_router(security_news_router)
app.include_router(reports_router)
app.include_router(notifications_router)
app.include_router(workspaces_router)
app.include_router(projects_router)


def _request_id_from(request: Request) -> str:
    return getattr(request.state, "request_id", None) or get_request_id() or "unknown"


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    request_id = _request_id_from(request)
    if exc.status_code >= 500:
        observe_error(request.method, request.url.path, "http_error")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "http_error", "message": str(exc.detail), "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Map every expected business failure onto the Phase 1.5 error envelope.

    ``exc.message`` is author-written and safe by construction; nothing from an
    upstream response, driver error or stack trace reaches the client here.
    """
    request_id = _request_id_from(request)
    observe_error(request.method, request.url.path, exc.error)
    if exc.status_code >= 500:
        logging.getLogger("backend.errors").warning(
            "application_error",
            extra={
                "request_id": request_id,
                "fields": {
                    "path": request.url.path,
                    "method": request.method,
                    "error": exc.error,
                    "status_code": exc.status_code,
                },
            },
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error, "message": exc.message, "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    request_id = _request_id_from(request)
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Invalid request.",
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id_from(request)
    observe_error(request.method, request.url.path, "unhandled_exception")
    logging.getLogger("backend.errors").exception(
        "unhandled_exception",
        extra={
            "request_id": request_id,
            "fields": {
                "path": request.url.path,
                "method": request.method,
                "exception_type": type(exc).__name__,
            },
        },
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred. Please try again later.",
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )
