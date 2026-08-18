"""Notification center service.

Real events, not a standalone CRUD island: AlertService/IncidentService/
RbacService call :meth:`NotificationService.notify_users` on genuine
triggers (a critical/high alert or incident created, a caller's own role
or active-state changed) - see each call site's comment for the exact
trigger condition and why.
"""

import uuid
from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_audit_event
from backend.core.exceptions import NotFoundError
from backend.repositories.notifications import NotificationRepository


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = NotificationRepository(session)

    async def create(self, *, user_id: uuid.UUID, actor: Optional[str], **values):
        record = await self._repo.create(user_id=user_id, **values)
        await self._session.commit()
        log_audit_event(
            event_type="notification",
            action="notification_created",
            resource=f"notification:{record.id}",
            result="success",
            actor=actor,
            metadata={"category": record.category, "severity": record.severity},
        )
        return record

    async def notify_users(
        self,
        user_ids: Sequence[uuid.UUID],
        *,
        title: str,
        body: str,
        category: str,
        severity: str,
        source_ref: str,
        actor: Optional[str],
    ) -> None:
        """Fan out one notification per recipient. Best-effort per user: one
        bad row must not stop the rest of the fan-out - the caller's own
        real event (the alert/incident/role-change) has already succeeded
        and committed by the time this runs, so a notification failure here
        must never roll that back."""
        for user_id in user_ids:
            try:
                await self._repo.create(
                    user_id=user_id,
                    title=title,
                    body=body,
                    category=category,
                    severity=severity,
                    source_ref=source_ref,
                )
            except Exception:  # noqa: BLE001 - notification delivery is best-effort
                continue  # nosec B112 - one bad recipient row must not stop the rest of the fan-out
        await self._session.commit()
        log_audit_event(
            event_type="notification",
            action="notification_fanout",
            resource=source_ref,
            result="success",
            actor=actor,
            metadata={"category": category, "severity": severity, "recipient_count": len(user_ids)},
        )

    async def list(self, *, user_id: uuid.UUID, page: int, page_size: int, unread_only: bool):
        return await self._repo.list(
            user_id=user_id, page=page, page_size=page_size, unread_only=unread_only
        )

    async def get(self, notification_id: uuid.UUID, *, user_id: uuid.UUID):
        record = await self._repo.get(notification_id, user_id=user_id)
        if record is None:
            raise NotFoundError("Không tìm thấy thông báo.")
        return record

    async def set_read(
        self, notification_id: uuid.UUID, *, user_id: uuid.UUID, is_read: bool, actor: Optional[str]
    ):
        record = await self.get(notification_id, user_id=user_id)
        record = await self._repo.set_read(record, is_read=is_read)
        await self._session.commit()
        log_audit_event(
            event_type="notification",
            action="notification_read_state_changed",
            resource=f"notification:{record.id}",
            result="success",
            actor=actor,
            metadata={"is_read": is_read},
        )
        return record
