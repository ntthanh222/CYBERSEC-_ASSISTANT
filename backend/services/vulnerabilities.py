"""Vulnerability management service."""
import uuid
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_audit_event
from backend.core.exceptions import ConflictError, InvalidRequestError, NotFoundError
from backend.repositories.vulnerabilities import PatchTaskRepository, VulnerabilityRepository


class VulnerabilityService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._vulns = VulnerabilityRepository(session)
        self._tasks = PatchTaskRepository(session)

    async def create(self, *, user_id: uuid.UUID, actor: Optional[str], **values):
        if values["updated_date"] < values["published_date"]:
            raise InvalidRequestError("Ngày cập nhật không thể trước ngày công bố.")
        try:
            record = await self._vulns.create(user_id=user_id, **values)
            await self._session.flush()
            await self._tasks.create(
                user_id=user_id,
                vulnerability_id=record.id,
                asset_id=record.asset_id,
                asset_name="Tự động tạo",
                status="not_started",
                notes=""
            )
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("Lỗ hổng này đã được theo dõi.") from exc
        except Exception:
            await self._session.rollback()
            raise
        log_audit_event(
            event_type="vulnerability",
            action="vulnerability_created",
            resource=f"vulnerability:{record.id}",
            result="success",
            actor=actor,
            metadata={"cve_id": record.cve_id, "severity": record.severity},
        )
        return record

    async def list(self, *, user_id: uuid.UUID, page: int, page_size: int, **filters):
        return await self._vulns.list(user_id=user_id, page=page, page_size=page_size, **filters)

    async def get(self, vulnerability_id: uuid.UUID, *, user_id: uuid.UUID):
        record = await self._vulns.get(vulnerability_id, user_id=user_id)
        if record is None:
            raise NotFoundError("Không tìm thấy lỗ hổng.")
        return record

    async def set_watchlist(
        self,
        vulnerability_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
        watchlist: bool,
        actor: Optional[str],
    ):
        record = await self._vulns.set_watchlist(
            vulnerability_id,
            user_id=user_id,
            watchlist=watchlist,
        )
        if record is None:
            raise NotFoundError("Không tìm thấy lỗ hổng.")
        await self._session.commit()
        log_audit_event(
            event_type="vulnerability",
            action="vulnerability_watchlist_updated",
            resource=f"vulnerability:{record.id}",
            result="success",
            actor=actor,
            metadata={"watchlist": record.watchlist},
        )
        return record

    async def create_patch_task(self, *, user_id: uuid.UUID, actor: Optional[str], **values):
        vulnerability = await self._vulns.get(values["vulnerability_id"], user_id=user_id)
        if vulnerability is None:
            raise NotFoundError("Không tìm thấy lỗ hổng.")
        record = await self._tasks.create(user_id=user_id, **values)
        await self._session.commit()
        log_audit_event(
            event_type="vulnerability",
            action="patch_task_created",
            resource=f"patch_task:{record.id}",
            result="success",
            actor=actor,
            metadata={"status": record.status},
        )
        return record, vulnerability

    async def list_patch_tasks(self, *, user_id: uuid.UUID, page: int, page_size: int):
        return await self._tasks.list(user_id=user_id, page=page, page_size=page_size)

    async def set_patch_status(
        self, task_id: uuid.UUID, *, user_id: uuid.UUID, status: str, actor: Optional[str]
    ):
        record = await self._tasks.set_status(task_id, user_id=user_id, status=status)
        if record is None:
            raise NotFoundError("Không tìm thấy nhiệm vụ vá lỗi.")
        await self._session.commit()
        log_audit_event(
            event_type="vulnerability",
            action="patch_task_status_updated",
            resource=f"patch_task:{record.id}",
            result="success",
            actor=actor,
            metadata={"status": record.status},
        )
        return record
