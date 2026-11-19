"""Database access for rulesets and gate runs."""
import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.gates.models import GateRun, Ruleset, RulesetVersion


class GateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ruleset(self, key: str, *, for_update: bool = False) -> Ruleset | None:
        statement = select(Ruleset).where(Ruleset.ruleset_key == key)
        if for_update:
            statement = statement.with_for_update()  # serialises drafting and approving per ruleset
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def rulesets(self) -> Sequence[Ruleset]:
        return (await self.session.execute(select(Ruleset).order_by(Ruleset.ruleset_key))).scalars().all()

    async def versions(self, keys: Iterable[str]) -> Sequence[RulesetVersion]:
        """Newest first, as the portal lists them."""
        result = await self.session.execute(
            select(RulesetVersion).where(RulesetVersion.ruleset_key.in_(list(keys)))
            .order_by(RulesetVersion.ruleset_key, RulesetVersion.version.desc())
        )
        return result.scalars().all()

    async def version(self, key: str, version: int) -> RulesetVersion | None:
        return await self.session.get(RulesetVersion, (key, version))

    async def max_version(self, key: str) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.max(RulesetVersion.version), 0)).where(RulesetVersion.ruleset_key == key)
        )
        return int(result.scalar_one())

    async def version_in_force(self, key: str, now: datetime) -> RulesetVersion | None:
        result = await self.session.execute(
            select(RulesetVersion)
            .where(RulesetVersion.ruleset_key == key, RulesetVersion.status == "approved",
                   or_(RulesetVersion.effective_from.is_(None), RulesetVersion.effective_from <= now))
            .order_by(RulesetVersion.version.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    def add_version(self, version: RulesetVersion) -> None:
        self.session.add(version)

    async def delete_version(self, key: str, version: int) -> None:
        await self.session.execute(
            delete(RulesetVersion).where(RulesetVersion.ruleset_key == key, RulesetVersion.version == version)
        )

    async def supersede_approved(self, key: str) -> None:
        await self.session.execute(
            update(RulesetVersion).where(RulesetVersion.ruleset_key == key, RulesetVersion.status == "approved")
            .values(status="superseded")
        )

    def add_run(self, run: GateRun) -> None:
        self.session.add(run)

    async def run(self, run_id: uuid.UUID) -> GateRun | None:
        return await self.session.get(GateRun, run_id)

    async def runs(self, run_ids: Iterable[uuid.UUID]) -> Sequence[tuple[GateRun, str]]:
        """The runs with their ruleset's name, oldest first."""
        wanted = list(run_ids)
        if not wanted:
            return []
        result = await self.session.execute(
            select(GateRun, Ruleset.name).join(Ruleset, Ruleset.ruleset_key == GateRun.ruleset_key)
            .where(GateRun.run_id.in_(wanted)).order_by(GateRun.evaluated_at)
        )
        return [(run, name) for run, name in result]
