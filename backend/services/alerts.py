"""Alert service."""
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_audit_event
from backend.core.exceptions import NotFoundError
from backend.repositories.alerts import AlertRepository
from backend.repositories.rbac import RbacRepository
from backend.services.notifications import NotificationService

#: Notifications fan out to admin-tier reviewers only for severities that
#: genuinely warrant real-time attention - a "low" alert creating a
#: notification for every admin would just be noise nobody reads.
_NOTIFY_SEVERITIES = ("critical", "high")


class AlertService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AlertRepository(session)

    async def create(self, *, user_id: uuid.UUID, actor: Optional[str], **values):
        record = await self._repo.create(user_id=user_id, **values)
        await self._session.commit()
        log_audit_event(
            event_type="alert",
            action="alert_created",
            resource=f"alert:{record.id}",
            result="success",
            actor=actor,
            metadata={"severity": record.severity, "status": record.status},
        )
        if record.severity in _NOTIFY_SEVERITIES:
            recipients = await RbacRepository(self._session).list_active_admin_tier_user_ids()
            await NotificationService(self._session).notify_users(
                recipients,
                title=f"Cảnh báo {record.severity} mới: {record.title}",
                body=record.description or "",
                category="alert",
                severity="critical" if record.severity == "critical" else "warning",
                source_ref=f"alert:{record.id}",
                actor=actor,
            )
        return record

    async def list(self, *, user_id: uuid.UUID, page: int, page_size: int, **filters):
        return await self._repo.list(user_id=user_id, page=page, page_size=page_size, **filters)

    async def get(self, alert_id: uuid.UUID, *, user_id: uuid.UUID):
        record = await self._repo.get(alert_id, user_id=user_id)
        if record is None:
            raise NotFoundError("Không tìm thấy cảnh báo.")
        return record

    async def set_status(
        self, alert_id: uuid.UUID, *, user_id: uuid.UUID, status: str, actor: Optional[str]
    ):
        record = await self._repo.set_status(alert_id, user_id=user_id, status=status)
        if record is None:
            raise NotFoundError("Không tìm thấy cảnh báo.")
        await self._session.commit()
        log_audit_event(
            event_type="alert",
            action="alert_status_updated",
            resource=f"alert:{record.id}",
            result="success",
            actor=actor,
            metadata={"status": record.status},
        )
        return record
