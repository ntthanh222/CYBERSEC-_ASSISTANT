"""Administration API: live summary, user/role management, audit trail.

Every route requires :func:`backend.core.authorization.require_admin`, which
re-reads the caller's role from the database on every request - a role
change or deactivation takes effect on the caller's very next request, not
just after their token expires.
"""
import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import PageParams, page_params
from backend.core.actor import get_current_actor
from backend.core.authorization import AppUser, require_admin
from backend.database.models.conversation import Conversation, Message
from backend.database.models.knowledge import KnowledgeDocument
from backend.database.models.scan_history import SecurityScanRecord
from backend.database.session import get_db, get_engine
from backend.schemas.health import ErrorResponse
from backend.schemas.rbac import (
    AdminActiveChangeRequest,
    AdminAuditLogPage,
    AdminContentCounts,
    AdminRoleChangeRequest,
    AdminSummaryResponse,
    AdminUserCounts,
    AdminUserItem,
    AdminUserMutationResponse,
    AdminUserPage,
    Role,
)
from backend.services.health import aggregate_status, check_database, check_redis
from backend.services.rbac import RbacService
from backend.services.security_news_crawler import crawler_status, run_security_news_crawler

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])

_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Administrator privileges required."}}
_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."}}


@router.get(
    "/summary",
    response_model=AdminSummaryResponse,
    summary="Live administration overview",
    description="Real counts across every user's data - never fixture data.",
    responses={**_UNAUTHORIZED, **_FORBIDDEN},
)
async def summary(session: AsyncSession = Depends(get_db)) -> AdminSummaryResponse:
    from backend.config.settings import get_settings
    from backend.database.models.rbac import ADMIN_TIER_ROLES, UserRole
    from backend.database.models.project import Project
    from backend.database.models.workspace import Workspace
    from backend.repositories.findings import FindingRepository
    from backend.repositories.project import ProjectRepository
    from backend.schemas.rbac import AdminProjectHealthItem
    from backend.services.project_dashboard import _score_from_counts

    settings = get_settings()

    total_users = await session.scalar(sa.select(sa.func.count()).select_from(UserRole))
    admins = await session.scalar(
        sa.select(sa.func.count())
        .select_from(UserRole)
        .where(UserRole.role.in_(ADMIN_TIER_ROLES))
    )
    active = await session.scalar(
        sa.select(sa.func.count()).select_from(UserRole).where(UserRole.is_active.is_(True))
    )
    documents = await session.scalar(sa.select(sa.func.count()).select_from(KnowledgeDocument))
    conversations = await session.scalar(sa.select(sa.func.count()).select_from(Conversation))
    messages = await session.scalar(sa.select(sa.func.count()).select_from(Message))
    scans = await session.scalar(sa.select(sa.func.count()).select_from(SecurityScanRecord))
    from backend.database.models.rbac import AdminAuditLog

    audit_events = await session.scalar(sa.select(sa.func.count()).select_from(AdminAuditLog))
    recent_since = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_admin_actions = await session.scalar(
        sa.select(sa.func.count())
        .select_from(AdminAuditLog)
        .where(AdminAuditLog.created_at >= recent_since)
    )
    role_counts = {
        row.role: int(row.count)
        for row in (
            await session.execute(
                sa.select(UserRole.role, sa.func.count().label("count")).group_by(UserRole.role)
            )
        ).all()
    }
    if session.bind and session.bind.dialect.name == "sqlite":
        source_counts = {}
    else:
        source_counts_rows = await session.execute(
            sa.text(
                """
                SELECT source, COUNT(*) AS count
                FROM (
                    SELECT
                        CASE
                            WHEN COALESCE(u.email, '') LIKE '%@example.test'
                                 OR COALESCE(u.email, '') LIKE '%.example.test' THEN 'test'
                            WHEN COALESCE(lac.username, '') LIKE 'demo_%'
                                 OR COALESCE(u.email, '') LIKE '%.demo.invalid' THEN 'demo'
                            WHEN lac.username IS NOT NULL THEN 'local'
                            ELSE 'hosted'
                        END AS source
                    FROM user_roles ur
                    JOIN auth.users u ON u.id = ur.user_id
                    LEFT JOIN local_admin_credentials lac ON lac.user_id = ur.user_id
                ) classified
                GROUP BY source
                """
            )
        )
        source_counts = {row.source: int(row.count) for row in source_counts_rows.all()}

    db_check = await check_database(get_engine())
    redis_check = await check_redis(settings.redis_url)
    system_status = aggregate_status({"database": db_check, "redis": redis_check})

    # -- Task 7: vuln-lifecycle admin overview additions ------------------
    # Every field below is a real aggregate query (or a pure function of
    # one), never a mocked/placeholder number - same "no fake data"
    # discipline as the rest of this endpoint.

    # Workspaces have no archived/active concept at all (Workspace has no
    # `status` column - see backend/database/models/workspace.py); every
    # workspace that exists is therefore counted as "active" here.
    active_workspaces = int(
        await session.scalar(sa.select(sa.func.count()).select_from(Workspace)) or 0
    )
    active_projects = int(
        await session.scalar(
            sa.select(sa.func.count()).select_from(Project).where(Project.status == "active")
        )
        or 0
    )

    findings_repo = FindingRepository(session)
    open_by_severity = await findings_repo.count_open_by_severity()
    open_findings = sum(open_by_severity.values())
    overdue_findings = await findings_repo.count_overdue()
    waiting_verify_findings = await findings_repo.count_by_status(status="fixed")
    fixed_since = datetime.now(timezone.utc) - timedelta(days=7)
    fixed_this_week_findings = await findings_repo.count_transitions_to_status_since(
        to_status="closed", since=fixed_since
    )

    # Project Health: bucket every *active* project by its Task 5 security
    # score - a modest N+1 (one aggregate query per active project), judged
    # acceptable here since this is an admin overview refreshed
    # occasionally, not a hot path (see the Task 7 brief).
    projects_repo = ProjectRepository(session)
    health_buckets = {"healthy": 0, "warning": 0, "critical": 0}
    for project in await projects_repo.list_active():
        project_open_by_severity = await findings_repo.count_open_by_severity(
            project_id=project.id
        )
        score = _score_from_counts(project_open_by_severity)
        if score >= 80:
            health_buckets["healthy"] += 1
        elif score >= 50:
            health_buckets["warning"] += 1
        else:
            health_buckets["critical"] += 1
    project_health = [
        AdminProjectHealthItem(bucket=bucket, count=count)
        for bucket, count in health_buckets.items()
    ]

    total_users = int(total_users or 0)
    admins = int(admins or 0)
    active = int(active or 0)
    return AdminSummaryResponse(
        users=AdminUserCounts(
            total=total_users,
            admins=admins,
            active=active,
            disabled=total_users - active,
            users=role_counts.get("user", 0),
            security_analysts=role_counts.get("security_analyst", 0),
            super_admins=role_counts.get("super_admin", 0),
            demo=source_counts.get("demo", 0),
            test=source_counts.get("test", 0),
            local=source_counts.get("local", 0),
            hosted=source_counts.get("hosted", 0),
        ),
        content=AdminContentCounts(
            documents=int(documents or 0),
            conversations=int(conversations or 0),
            messages=int(messages or 0),
            scans=int(scans or 0),
        ),
        system_status=system_status,
        audit_events=int(audit_events or 0),
        recent_admin_actions=int(recent_admin_actions or 0),
        active_workspaces=active_workspaces,
        active_projects=active_projects,
        open_findings=open_findings,
        critical_findings=open_by_severity.get("critical", 0),
        high_findings=open_by_severity.get("high", 0),
        overdue_findings=overdue_findings,
        waiting_verify_findings=waiting_verify_findings,
        fixed_this_week_findings=fixed_this_week_findings,
        project_health=project_health,
    )


@router.get(
    "/users",
    response_model=AdminUserPage,
    summary="List every identity that has an app role",
    responses={**_UNAUTHORIZED, **_FORBIDDEN},
)
async def list_users(
    pagination: PageParams = Depends(page_params),
    search: str | None = Query(default=None, max_length=128),
    role: Role | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(active|disabled)$"),
    source: str | None = Query(default=None, pattern="^(demo|test|local|hosted)$"),
    hide_test_accounts: bool = Query(default=True),
    session: AsyncSession = Depends(get_db),
) -> AdminUserPage:
    service = RbacService(session)
    items, total = await service.list_users(
        page=pagination.page,
        page_size=pagination.page_size,
        search=search,
        role=role,
        status=status,
        source=source,
        hide_test_accounts=hide_test_accounts,
    )
    return AdminUserPage(
        items=[
            AdminUserItem(
                user_id=str(item["user_id"]),
                email=item.get("email"),
                username=item.get("username"),
                role=item["role"],
                is_active=item["is_active"],
                source=item.get("source") or "hosted",
                is_test_account=bool(item.get("is_test_account")),
                created_at=item["created_at"],
                updated_at=item["updated_at"],
                last_login_at=item.get("last_login_at"),
            )
            for item in items
        ],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.patch(
    "/users/{user_id}/role",
    response_model=AdminUserMutationResponse,
    summary="Change a user's role",
    description="Blocked with 409 if this would leave the system with zero active administrators.",
    responses={
        **_UNAUTHORIZED,
        **_FORBIDDEN,
        404: {"model": ErrorResponse, "description": "User not found."},
        409: {"model": ErrorResponse, "description": "Would remove the last active administrator."},
    },
)
async def change_role(
    user_id: uuid.UUID,
    payload: AdminRoleChangeRequest,
    admin: AppUser = Depends(require_admin),
    actor: str = Depends(get_current_actor),
    session: AsyncSession = Depends(get_db),
) -> AdminUserMutationResponse:
    service = RbacService(session)
    result = await service.change_role(
        user_id, new_role=payload.role, actor_user_id=admin.id, actor_role=admin.role, actor=actor
    )
    return AdminUserMutationResponse(
        user_id=str(result["user_id"]), role=result["role"], is_active=result["is_active"]
    )


@router.patch(
    "/users/{user_id}/active",
    response_model=AdminUserMutationResponse,
    summary="Activate or deactivate a user",
    description="Blocked with 409 if this would leave the system with zero active administrators.",
    responses={
        **_UNAUTHORIZED,
        **_FORBIDDEN,
        404: {"model": ErrorResponse, "description": "User not found."},
        409: {"model": ErrorResponse, "description": "Would remove the last active administrator."},
    },
)
async def change_active(
    user_id: uuid.UUID,
    payload: AdminActiveChangeRequest,
    admin: AppUser = Depends(require_admin),
    actor: str = Depends(get_current_actor),
    session: AsyncSession = Depends(get_db),
) -> AdminUserMutationResponse:
    service = RbacService(session)
    result = await service.set_active(
        user_id,
        is_active=payload.is_active,
        actor_user_id=admin.id,
        actor_role=admin.role,
        actor=actor,
    )
    return AdminUserMutationResponse(
        user_id=str(result["user_id"]), role=result["role"], is_active=result["is_active"]
    )


@router.get(
    "/audit",
    response_model=AdminAuditLogPage,
    summary="Recent administrative actions",
    responses={**_UNAUTHORIZED, **_FORBIDDEN},
)
async def audit_log(
    pagination: PageParams = Depends(page_params),
    search: str | None = Query(default=None, max_length=128),
    action: str | None = Query(default=None, max_length=64),
    actor_user_id: uuid.UUID | None = Query(default=None),
    target_user_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> AdminAuditLogPage:
    service = RbacService(session)
    items, total = await service.list_audit_log(
        page=pagination.page,
        page_size=pagination.page_size,
        search=search,
        action=action,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
    )
    return AdminAuditLogPage(
        items=[
            {
                "id": str(item.id),
                "actor_user_id": str(item.actor_user_id) if item.actor_user_id else None,
                "action": item.action,
                "target_user_id": str(item.target_user_id) if item.target_user_id else None,
                "metadata": item.meta,
                "created_at": item.created_at,
            }
            for item in items
        ],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/crawler",
    summary="Security News crawler status",
    responses={**_UNAUTHORIZED, **_FORBIDDEN},
)
async def get_crawler_status() -> dict:
    return crawler_status()


@router.post(
    "/crawler/run",
    summary="Run Security News crawler now",
    responses={**_UNAUTHORIZED, **_FORBIDDEN},
)
async def run_crawler_now(
    admin: AppUser = Depends(require_admin),
    actor: str = Depends(get_current_actor),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await run_security_news_crawler(session, user_id=admin.id, actor=actor)
