"""Database access for statements and their lines."""
import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.statements.models import NavDetail, Statement, StatementLine


class StatementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, statement_id: uuid.UUID, *, for_update: bool = False) -> Statement | None:
        statement = select(Statement).where(Statement.statement_id == statement_id)
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def by_object_key(self, object_key: str) -> Statement | None:
        result = await self.session.execute(select(Statement).where(Statement.object_key == object_key))
        return result.scalar_one_or_none()

    async def lines(self, statement_id: uuid.UUID) -> Sequence[StatementLine]:
        result = await self.session.execute(
            select(StatementLine).where(StatementLine.statement_id == statement_id).order_by(StatementLine.line_no)
        )
        return result.scalars().all()

    async def line_for_update(self, statement_id: uuid.UUID, line_id: uuid.UUID) -> StatementLine | None:
        result = await self.session.execute(
            select(StatementLine)
            .where(StatementLine.statement_id == statement_id, StatementLine.line_id == line_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def progress(self, statement_id: uuid.UUID) -> tuple[int, int]:
        """(approved lines, all lines)."""
        result = await self.session.execute(
            select(func.count().filter(StatementLine.approved.is_(True)), func.count())
            .where(StatementLine.statement_id == statement_id)
        )
        approved, total = result.one()
        return int(approved), int(total)

    async def add(self, statement: Statement) -> None:
        self.session.add(statement)
        await self.session.flush()

    async def replace_lines(self, statement_id: uuid.UUID, lines: Sequence[StatementLine]) -> None:
        """A re-extraction replaces every line (the Maker's review starts again)."""
        await self.session.execute(delete(StatementLine).where(StatementLine.statement_id == statement_id))
        self.session.add_all(lines)

    async def nav_detail(self, statement_id: uuid.UUID) -> NavDetail | None:
        return await self.session.get(NavDetail, statement_id)

    async def replace_nav_detail(self, detail: NavDetail) -> None:
        await self.session.execute(delete(NavDetail).where(NavDetail.statement_id == detail.statement_id))
        self.session.add(detail)

    async def registered_before(self, kind: str, before: datetime) -> Sequence[Statement]:
        """Statements still waiting for their extraction job: the workflow stopped after intake."""
        result = await self.session.execute(
            select(Statement).where(Statement.kind == kind, Statement.state == "REGISTERED",
                                    Statement.created_at < before)
        )
        return result.scalars().all()
