"""Database access for extraction jobs."""
import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.extraction.models import ExtractionJob


class ExtractionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_update(self, job_id: uuid.UUID) -> ExtractionJob | None:
        result = await self.session.execute(
            select(ExtractionJob).where(ExtractionJob.job_id == job_id).with_for_update()
        )
        return result.scalar_one_or_none()

    def add(self, job: ExtractionJob) -> None:
        self.session.add(job)

    async def stuck(self, before: datetime) -> Sequence[ExtractionJob]:
        """Jobs that should have finished by `before`: still queued or running, or finished with n8n never told."""
        result = await self.session.execute(
            select(ExtractionJob).where(or_(
                and_(ExtractionJob.status.in_(("QUEUED", "RUNNING")), ExtractionJob.created_at < before),
                and_(ExtractionJob.status.in_(("SUCCEEDED", "FAILED")), ExtractionJob.callback_acked.is_(False),
                     ExtractionJob.finished_at < before),
            ))
        )
        return result.scalars().all()
