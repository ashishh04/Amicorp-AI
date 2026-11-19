"""Database access for notifications."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, notification: Notification) -> None:
        self.session.add(notification)
        await self.session.flush()

    async def get_for_update(self, notification_id: uuid.UUID) -> Notification | None:
        result = await self.session.execute(
            select(Notification).where(Notification.notification_id == notification_id).with_for_update()
        )
        return result.scalar_one_or_none()
