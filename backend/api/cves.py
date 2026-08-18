"""CVE lookup endpoints.

**Requires a valid Supabase Auth Bearer token on every route** (Phase 2.5B).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.actor import get_current_actor
from backend.core.auth import AuthenticatedUser, get_current_user
from backend.core.exceptions import NotFoundError
from backend.core.rate_limit import rate_limit
from backend.database.session import get_rls_db
from backend.schemas.cves import CveResponse, CveSearchResponse
from backend.schemas.health import ErrorResponse
from backend.services.cve import CveLookupService
from backend.services.scan_history import ScanHistoryService

router = APIRouter(
    prefix="/api/cves", tags=["cves"], dependencies=[Depends(get_current_user)]
)
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}

cve_rate_limit = rate_limit(bucket="cve_lookup", limit=30, window_seconds=60)


@router.get(
    "/search",
    summary="Search CVEs by keyword",
    description=(
        "Free-text search against the upstream NVD database. Results are not "
        "cached (only single-id lookups are); each call reaches the upstream "
        "provider."
    ),
    response_description="Matching CVE records.",
    response_model=CveSearchResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Missing or invalid query."},
        429: {"model": ErrorResponse, "description": "Rate limited."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
        504: {"model": ErrorResponse, "description": "Upstream provider timed out."},
        **_UNAUTHORIZED,
    },
    dependencies=[Depends(cve_rate_limit)],
)
async def search_cves(
    q: str = Query(..., min_length=1, max_length=200, examples=["log4j"]),
    limit: int = Query(default=10, ge=1, le=50),
) -> dict:
    service = CveLookupService()
    results = await service.search(q, limit=limit)
    return {"query": q, "results": results, "count": len(results)}


@router.get(
    "/{cve_id}",
    summary="Look up a single CVE",
    description=(
        "Fetches a CVE record from the public NVD API, cached in Redis for a "
        "configurable TTL. `cached` in the response distinguishes a cache hit "
        "from a fresh upstream fetch. When the record is not found upstream, "
        "returns 404 - never fabricated data. When Redis is unavailable, the "
        "lookup still succeeds against the upstream provider; only the cache "
        "is skipped."
    ),
    response_description="The CVE record.",
    response_model=CveResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Malformed CVE id."},
        404: {"model": ErrorResponse, "description": "CVE not found upstream."},
        429: {"model": ErrorResponse, "description": "Rate limited."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
        504: {"model": ErrorResponse, "description": "Upstream provider timed out."},
        **_UNAUTHORIZED,
    },
    dependencies=[Depends(cve_rate_limit)],
)
async def get_cve(
    cve_id: str,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict:
    service = CveLookupService()
    history = ScanHistoryService(session)

    try:
        result = await service.get(cve_id, actor=actor)
    except NotFoundError:
        await history.record(
            scan_type="cve_lookup",
            target=cve_id.strip().upper()[:2048],
            status="failed",
            summary="CVE not found",
            user_id=user.id,
            actor=actor,
        )
        raise

    await history.record(
        scan_type="cve_lookup",
        target=result["cve_id"],
        status="completed",
        summary=f"{result['cve_id']}: {result.get('severity') or 'unknown'} "
        f"(CVSS {result.get('cvss_score')})"[:500],
        risk_score=(
            round(result["cvss_score"] * 10) if result.get("cvss_score") is not None else None
        ),
        severity=result.get("severity"),
        details={"source": result["source"], "cached": result["cached"]},
        user_id=user.id,
        actor=actor,
    )
    return result
