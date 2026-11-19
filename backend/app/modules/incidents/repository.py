"""Database access for incidents."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.incidents.models import Incident


class IncidentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, incident_id: uuid.UUID) -> Incident | None:
        return await self.session.get(Incident, incident_id)

    async def get_by_key(self, incident_key: str) -> Incident | None:
        result = await self.session.execute(select(Incident).where(Incident.incident_key == incident_key))
        return result.scalar_one_or_none()

    def add(self, incident: Incident) -> None:
        self.session.add(incident)
