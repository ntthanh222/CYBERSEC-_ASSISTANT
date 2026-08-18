"""Asset inventory endpoints (Phase 3, Task #5).

**Requires a valid Supabase Auth Bearer token on every route.** Only the
caller's own assets are visible or mutable - see ``backend.services.assets``
and the RLS policy on ``assets`` in migration 0007.
"""
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.core.actor import get_current_actor
from backend.core.auth import AuthenticatedUser, get_current_user
from backend.database.models.asset import Asset
from backend.database.session import get_rls_db
from backend.schemas.assets import AssetCreate, AssetItem, AssetPage
from backend.schemas.health import ErrorResponse
from backend.services.assets import AssetService

router = APIRouter(
    prefix="/api/assets", tags=["assets"], dependencies=[Depends(get_current_user)]
)
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}


def _asset_dict(record: Asset) -> dict[str, Any]:
    return {
        "id": record.id,
        "name": record.name,
        "type": record.type,
        "hostname": record.hostname,
        "ip_address": record.ip_address,
        "operating_system": record.operating_system,
        "owner": record.owner,
        "department": record.department,
        "business_criticality": record.business_criticality,
        "internet_exposed": record.internet_exposed,
        "description": record.description,
        "linked_cves": record.linked_cves,
        "patch_status": record.patch_status,
        "exploit_evidence": record.exploit_evidence,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@router.post(
    "",
    status_code=201,
    summary="Add an asset to the inventory",
    description="Creates one asset owned by the caller. There is no external "
    "feed for this data - it is always analyst-entered.",
    response_description="The created asset.",
    response_model=AssetItem,
    responses={422: {"model": ErrorResponse, "description": "Invalid body."}, **_UNAUTHORIZED},
)
async def create_asset(
    body: AssetCreate,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
    actor: str = Depends(get_current_actor),
) -> dict:
    service = AssetService(session)
    record = await service.create(
        user_id=user.id,
        name=body.name,
        type=body.type,
        hostname=body.hostname,
        ip_address=body.ip_address,
        operating_system=body.operating_system,
        owner=body.owner,
        department=body.department,
        business_criticality=body.business_criticality,
        internet_exposed=body.internet_exposed,
        description=body.description,
        linked_cves=body.linked_cves,
        patch_status=body.patch_status,
        exploit_evidence=body.exploit_evidence,
        actor=actor,
    )
    return _asset_dict(record)


@router.get(
    "",
    summary="List assets",
    description="The caller's own asset inventory, newest first by default.",
    response_description="A page of assets.",
    response_model=AssetPage,
    responses={
        422: {"model": ErrorResponse, "description": "Invalid query parameters."},
        **_UNAUTHORIZED,
    },
)
async def list_assets(
    pagination: PageParams = Depends(page_params),
    type: Optional[str] = Query(default=None),
    business_criticality: Optional[str] = Query(default=None),
    sort: str = Query(default="desc", pattern="^(asc|desc)$"),
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    service = AssetService(session)
    items, total = await service.list(
        user_id=user.id,
        page=pagination.page,
        page_size=pagination.page_size,
        type=type,
        business_criticality=business_criticality,
        sort=sort,
    )
    return {
        "items": [_asset_dict(item) for item in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get(
    "/{asset_id}",
    summary="Get one asset",
    description="Only the owning caller can see it.",
    response_description="The asset.",
    response_model=AssetItem,
    responses={404: {"model": ErrorResponse, "description": "Asset not found."}, **_UNAUTHORIZED},
)
async def get_asset(
    asset_id: UUID,
    session: AsyncSession = Depends(get_rls_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    service = AssetService(session)
    record = await service.get(asset_id, user_id=user.id)
    return _asset_dict(record)
