"""Database access for scans."""
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.scans.models import Finding, Scan


class ScanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, scan_id: uuid.UUID) -> Scan | None:
        return await self.session.get(Scan, scan_id)

    async def get_for_update(self, scan_id: uuid.UUID) -> Scan | None:
        result = await self.session.execute(select(Scan).where(Scan.scan_id == scan_id).with_for_update())
        return result.scalar_one_or_none()

    async def get_finding(self, finding_id: uuid.UUID) -> Finding | None:
        return await self.session.get(Finding, finding_id)

    async def new_findings(self, scan_id: uuid.UUID, limit: int) -> Sequence[Finding]:
        result = await self.session.execute(
            select(Finding).where(Finding.scan_id == scan_id, Finding.is_new.is_(True))
            .order_by(Finding.new_rank).limit(limit)
        )
        return result.scalars().all()

    async def add(self, scan: Scan) -> None:
        self.session.add(scan)
        await self.session.flush()

    def add_finding(self, finding: Finding) -> None:
        self.session.add(finding)
