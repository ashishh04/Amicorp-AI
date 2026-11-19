"""Reference lookups. Repository-light: small tables, read-only for the API."""
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import or_, select

from app.db.session import UnitOfWork
from app.modules.lookups.models import Bank, CountryRisk, EnNumber, FundTemplate, NamedList
from app.modules.lookups.schemas import LookupEntry

MAX_RESULTS = 50


async def search_en_numbers(uow: UnitOfWork, q: str | None) -> list[LookupEntry]:
    async with uow:
        statement = select(EnNumber).order_by(EnNumber.code).limit(MAX_RESULTS)
        if q:
            pattern = f"%{q.strip()}%"
            statement = statement.where(or_(EnNumber.code.ilike(pattern), EnNumber.name.ilike(pattern)))
        rows = (await uow.session.execute(statement)).scalars().all()
    return [LookupEntry(code=r.code, name=r.name) for r in rows]


async def en_number_names(uow: UnitOfWork, codes: Iterable[str]) -> dict[str, str]:
    """Which of these codes are in today's table, with their names. Call inside an open unit of work."""
    wanted = [c for c in set(codes) if c]
    if not wanted:
        return {}
    rows = (await uow.session.execute(select(EnNumber).where(EnNumber.code.in_(wanted)))).scalars().all()
    return {r.code: r.name for r in rows}


async def bank_bic(uow: UnitOfWork, bank_name: str | None) -> str | None:
    """The BIC on file for a bank, or None when the bank is not in the table. Call inside a unit of work."""
    if not bank_name:
        return None
    bank = await uow.session.get(Bank, bank_name)
    return bank.bic if bank else None


async def rule_reference(uow: UnitOfWork) -> tuple[dict[str, frozenset[str]], dict[str, str]]:
    """The named lists and the country-risk table the rules read. Call inside a unit of work."""
    lists: dict[str, set[str]] = defaultdict(set)
    for row in (await uow.session.execute(select(NamedList))).scalars():
        lists[row.list_name].add(row.value)
    risk = {row.country: row.risk for row in (await uow.session.execute(select(CountryRisk))).scalars()}
    return {name: frozenset(values) for name, values in lists.items()}, risk


async def fund_tolerance(uow: UnitOfWork, fund_code: str, share_class: str) -> Decimal | None:
    """The NAV move (percent) a fund's share class tolerates, or None when it has no template."""
    template = await uow.session.get(FundTemplate, (fund_code, share_class))
    return template.tolerance_pct if template else None
