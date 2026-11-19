"""Database access for maintenance."""
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.maintenance.models import Redrive


class RedriveRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, scope: str, item_id: str) -> Redrive | None:
        return await self.session.get(Redrive, (scope, item_id), with_for_update=True)

    def start(self, scope: str, item_id: str, now: datetime) -> Redrive:
        row = Redrive(scope=scope, item_id=item_id, attempts=0, last_redriven_at=now, escalated_at=None)
        self.session.add(row)
        return row
