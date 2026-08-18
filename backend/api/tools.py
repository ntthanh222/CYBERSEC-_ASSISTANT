"""Security Toolkit endpoints: URL scanner and password strength checker.

**Requires a valid Supabase Auth Bearer token on every route** (Phase 2.5B) -
including the stateless password tools, for rate-limiting, audit, and abuse
prevention as much as for ownership.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.actor import get_current_actor
from backend.core.audit import log_audit_event
from backend.core.auth import AuthenticatedUser, get_current_user
from backend.core.exceptions import BlockedTargetError
from backend.core.metrics import observe_password_check, observe_url_scan
from backend.core.rate_limit import rate_limit
from backend.database.session import get_rls_db
from backend.schemas.health import ErrorResponse
from backend.schemas.tools import (
    PasswordCheckRequest,
    PasswordCheckResponse,
    PasswordGuidanceResponse,
    PasswordStrength,
    UrlScanRequest,
    UrlScanResponse,
)
from backend.services.password_strength import GUIDANCE, analyse
from backend.services.scan_history import ScanHistoryService
from backend.services.url_scanner import blocked_summary, scan_url, summarize

router = APIRouter(
    prefix="/api/tools", tags=["tools"], dependencies=[Depends(get_current_user)]
)
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}

url_scan_rate_limit = rate_limit(bucket="url_scan", limit=20, window_seconds=60)
password_check_rate_limit = rate_limit(bucket="password_check", limit=60, window_seconds=60)


@router.post(
    "/url-scan",
    summary="Scan a URL for SSRF-safe risk indicators",
    description=(
        "Validates and inspects a URL: scheme allowlist, hostname resolution, "
        "SSRF blocking of private/loopback/link-local/metadata addresses, "
        "bounded redirects re-validated at every hop, response-size cap, and a "
        "risk score built from concrete findings. A target refused by the SSRF "
        "guard returns 400; a target that resolves but cannot be reached "
        "returns 200 with `status: \"failed\"`, matching the platform's "
        "convention of not confusing a transport failure with an API error. "
        "Every scan is written to scan history."
    ),
    response_description="The scan result plus its findings and recommendations.",
    response_model=UrlScanResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid URL or blocked by the SSRF guard."},
        422: {"model": ErrorResponse, "description": "Request body failed validation."},
        429: {"model": ErrorResponse, "description": "Rate limited."},
        **_UNAUTHORIZED,
    },
    dependencies=[Depends(url_scan_rate_limit)],
)
async def url_scan(
    payload: UrlScanRequest,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict:
    history = ScanHistoryService(session)
    try:
        result = await scan_url(payload.url)
    except BlockedTargetError as exc:
        record = await history.record(
            scan_type="url_scan",
            target=payload.url[:2048],
            status="failed",
            summary=blocked_summary(exc),
            user_id=user.id,
            actor=actor,
        )
        observe_url_scan("blocked")
        log_audit_event(
            event_type="url_scan",
            action="scan_executed",
            resource=f"scan_history:{record.id}",
            result="failure",
            actor=actor,
            metadata={"outcome": "blocked", "error": exc.error},
        )
        raise

    status = "completed" if result["reachable"] else "failed"
    record = await history.record(
        scan_type="url_scan",
        target=result["normalized_url"][:2048],
        status=status,
        summary=summarize(result)[:500],
        risk_score=result["risk_score"],
        severity=result["severity"],
        details={"findings": result["findings"], "recommendations": result["recommendations"]},
        user_id=user.id,
        actor=actor,
    )
    observe_url_scan(result["status"], result["duration_ms"] / 1000)
    log_audit_event(
        event_type="url_scan",
        action="scan_executed",
        resource=f"scan_history:{record.id}",
        result="success",
        actor=actor,
        metadata={"outcome": result["status"], "risk_score": result["risk_score"]},
    )

    return {**result, "id": record.id, "created_at": record.created_at}


@router.post(
    "/password-check",
    summary="Analyse password strength (stateless)",
    description=(
        "Scores length, entropy, character variety, repeated/sequential "
        "patterns and known-common passwords. **The password is never "
        "persisted, logged, echoed back, or used as a metric label** - only the "
        "resulting strength bucket is counted. No network call is made; the "
        "common-password check runs against a bundled offline list."
    ),
    response_description="Derived strength facts. Never includes the password.",
    response_model=PasswordCheckResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Request body failed validation."},
        429: {"model": ErrorResponse, "description": "Rate limited."},
        **_UNAUTHORIZED,
    },
    dependencies=[Depends(password_check_rate_limit)],
)
async def password_check(payload: PasswordCheckRequest) -> dict:
    result = analyse(payload.password)
    observe_password_check(result["strength"])
    return result


@router.get(
    "/password-guidance",
    summary="Static advice for a strength bucket",
    description=(
        "Returns canned guidance text for one of the four strength buckets. "
        "Intended for a client-side password checker (which never sends the "
        "password itself) to fetch matching advice by bucket name."
    ),
    response_description="Static guidance for the requested strength.",
    response_model=PasswordGuidanceResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Unknown strength bucket."},
        **_UNAUTHORIZED,
    },
)
async def password_guidance(
    strength: PasswordStrength = Query(..., examples=["weak"]),
) -> dict:
    # `strength` is a Literal of the exact GUIDANCE keys, so FastAPI's own
    # validation already rejects anything else with a 422 before this runs.
    return GUIDANCE[strength]
