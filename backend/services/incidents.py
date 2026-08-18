"""Incident response service."""

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_audit_event
from backend.core.exceptions import NotFoundError
from backend.core.timeutils import utcnow
from backend.repositories.incidents import (
    IncidentRepository,
    IncidentTaskRepository,
    IncidentTimelineRepository,
)
from backend.repositories.rbac import RbacRepository
from backend.services.notifications import NotificationService


class IncidentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._incidents = IncidentRepository(session)
        self._tasks = IncidentTaskRepository(session)
        self._timeline = IncidentTimelineRepository(session)

    async def create(self, *, user_id: uuid.UUID, actor: Optional[str], **values):
        record = await self._incidents.create(user_id=user_id, **values)
        await self._timeline.create(
            user_id=user_id,
            incident_id=record.id,
            event_type="created",
            message=f"Đã tạo sự cố với mức độ nghiêm trọng {record.severity}.",
            actor=actor,
        )
        await self._session.commit()
        log_audit_event(
            event_type="incident",
            action="incident_created",
            resource=f"incident:{record.id}",
            result="success",
            actor=actor,
            metadata={"severity": record.severity, "status": record.status},
        )
        # A critical incident is the one event category where every
        # admin-tier reviewer genuinely needs to know immediately - high
        # incidents already get SOC attention via the incident list itself.
        if record.severity == "critical":
            recipients = await RbacRepository(self._session).list_active_admin_tier_user_ids()
            await NotificationService(self._session).notify_users(
                recipients,
                title=f"Đã mở sự cố nghiêm trọng: {record.title}",
                body=record.description or "",
                category="incident",
                severity="critical",
                source_ref=f"incident:{record.id}",
                actor=actor,
            )
        return record

    async def list(self, *, user_id: uuid.UUID, page: int, page_size: int, **filters):
        return await self._incidents.list(
            user_id=user_id, page=page, page_size=page_size, **filters
        )

    async def get_detail(self, incident_id: uuid.UUID, *, user_id: uuid.UUID):
        incident = await self._incidents.get(incident_id, user_id=user_id)
        if incident is None:
            raise NotFoundError("Không tìm thấy sự cố.")
        tasks = await self._tasks.list_for_incident(incident.id, user_id=user_id)
        timeline = await self._timeline.list_for_incident(incident.id, user_id=user_id)
        return incident, tasks, timeline

    async def set_status(
        self, incident_id: uuid.UUID, *, user_id: uuid.UUID, status: str, actor: Optional[str]
    ):
        closed_at = utcnow() if status == "closed" else None
        incident = await self._incidents.set_status(
            incident_id,
            user_id=user_id,
            status=status,
            closed_at=closed_at,
        )
        if incident is None:
            raise NotFoundError("Không tìm thấy sự cố.")
        await self._timeline.create(
            user_id=user_id,
            incident_id=incident.id,
            event_type="status",
            message=f"Đã đổi trạng thái sự cố thành {status}.",
            actor=actor,
        )
        await self._session.commit()
        log_audit_event(
            event_type="incident",
            action="incident_status_updated",
            resource=f"incident:{incident.id}",
            result="success",
            actor=actor,
            metadata={"status": incident.status},
        )
        return incident

    async def create_task(
        self, incident_id: uuid.UUID, *, user_id: uuid.UUID, actor: Optional[str], **values
    ):
        incident = await self._incidents.get(incident_id, user_id=user_id)
        if incident is None:
            raise NotFoundError("Không tìm thấy sự cố.")
        task = await self._tasks.create(user_id=user_id, incident_id=incident.id, **values)
        await self._timeline.create(
            user_id=user_id,
            incident_id=incident.id,
            event_type="task",
            message=f"Đã thêm nhiệm vụ: {task.title}.",
            actor=actor,
        )
        await self._session.commit()
        return task

    async def set_task_status(
        self, task_id: uuid.UUID, *, user_id: uuid.UUID, status: str, actor: Optional[str]
    ):
        task = await self._tasks.set_status(task_id, user_id=user_id, status=status)
        if task is None:
            raise NotFoundError("Không tìm thấy nhiệm vụ của sự cố.")
        await self._timeline.create(
            user_id=user_id,
            incident_id=task.incident_id,
            event_type="task",
            message=f"Nhiệm vụ '{task.title}' đã đổi trạng thái thành {status}.",
            actor=actor,
        )
        await self._session.commit()
        return task

    async def add_note(
        self, incident_id: uuid.UUID, *, user_id: uuid.UUID, actor: Optional[str], message: str
    ):
        incident = await self._incidents.get(incident_id, user_id=user_id)
        if incident is None:
            raise NotFoundError("Không tìm thấy sự cố.")
        event = await self._timeline.create(
            user_id=user_id,
            incident_id=incident.id,
            event_type="note",
            message=message,
            actor=actor,
        )
        await self._session.commit()
        return event
