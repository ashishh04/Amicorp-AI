"""Database access for the user directory."""
import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import AppUser


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID) -> AppUser | None:
        return await self.session.get(AppUser, user_id)

    async def many(self, user_ids: Iterable[uuid.UUID]) -> Sequence[AppUser]:
        wanted = list(set(user_ids))
        if not wanted:
            return []
        return (await self.session.execute(select(AppUser).where(AppUser.user_id.in_(wanted)))).scalars().all()

    async def named_like(self, pattern: str) -> Sequence[AppUser]:
        """People whose display name matches an ILIKE pattern (escaped with backslash)."""
        result = await self.session.execute(select(AppUser).where(AppUser.display_name.ilike(pattern, escape="\\")))
        return result.scalars().all()

    async def active(self) -> Sequence[AppUser]:
        result = await self.session.execute(
            select(AppUser).where(AppUser.active.is_(True)).order_by(AppUser.display_name)
        )
        return result.scalars().all()
