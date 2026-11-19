"""Read-only reporting queries for the KPI dashboard.

The one place that reads across modules' tables: aggregates over cards, gate runs and statements, with no
business rules and no writes, so it cannot change what any module owns. Days are UTC days.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

OPEN = ["NEW", "ASSEMBLING", "AWAITING_DECISION", "ESCALATED", "WRITING_BACK", "WRITEBACK_FAILED"]

# A breach: a card still waiting at its due time (not approved or rejected by then).
_BREACHES = """
    SELECT {group} AS k, count(*) AS n FROM card.card c
     WHERE c.due_at >= :lo AND c.due_at < :hi
       AND NOT EXISTS (SELECT 1 FROM card.card_event e WHERE e.card_id = c.card_id
                          AND e.to_state IN ('APPROVED','REJECTED') AND e.at <= c.due_at)
     GROUP BY 1"""

# UC1 fields, and those below the statement's threshold (a corrected field counts too: it was flagged or wrong).
_FIELDS = """
    SELECT {group} AS k, count(*) AS total,
           count(*) FILTER (WHERE kv.value::numeric < coalesce(s.threshold, 0.70) OR kv.key = ANY(l.corrected)) AS low
      FROM stmt.statement s
      JOIN stmt.statement_line l ON l.statement_id = s.statement_id
      CROSS JOIN LATERAL jsonb_each_text(l.confidence) AS kv
     WHERE s.kind = 'bank' AND s.extracted_at >= :lo AND s.extracted_at < :hi
     GROUP BY 1"""

_EVENTS = """
    SELECT {group} AS k,
           count(*) FILTER (WHERE to_state IN ('APPROVED','REJECTED')) AS decided,
           count(*) FILTER (WHERE from_state = 'WRITING_BACK' AND to_state = 'CLOSED') AS ok,
           count(*) FILTER (WHERE to_state = 'WRITEBACK_FAILED') AS failed
      FROM card.card_event WHERE at >= :lo AND at < :hi
     GROUP BY 1"""

_GATES = """
    SELECT {group} AS k,
           count(*) FILTER (WHERE ruleset_key = 'aml.gate1-entry') AS g1,
           count(*) FILTER (WHERE ruleset_key = 'aml.gate1-entry' AND outcome = 'monitor') AS monitor,
           percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95
      FROM rules.gate_run WHERE evaluated_at >= :lo AND evaluated_at < :hi
     GROUP BY 1"""

# Grouping expressions: fixed code, never input.
BY_DAY = {
    "card": "(c.due_at AT TIME ZONE 'UTC')::date",
    "field": "(s.extracted_at AT TIME ZONE 'UTC')::date",
    "event": "(at AT TIME ZONE 'UTC')::date",
    "gate": "(evaluated_at AT TIME ZONE 'UTC')::date",
}
ALL = "'all'"


@dataclass
class Figures:
    """One day's figures, or a whole period's."""

    created: int = 0
    decided: int = 0
    breaches: int = 0
    writebacks_ok: int = 0
    writebacks_failed: int = 0
    gate1_runs: int = 0
    gate1_monitor: int = 0
    gate_p95_ms: float | None = None
    fields: int = 0
    fields_low: int = 0
    breaches_by_team: dict[str, int] = field(default_factory=dict)
    low_by_bank: dict[str, tuple[int, int]] = field(default_factory=dict)  # bank: (fields, low)
    gate_outcomes: list[tuple[str, str, int]] = field(default_factory=list)


class DashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _rows(self, sql: str, **params: Any) -> list[Any]:
        return list((await self.session.execute(text(sql), params)).all())

    async def open_now(self, now: datetime) -> tuple[int, int, list[tuple[str, str, int]]]:
        """(open cards, critical cards past due, open cards by type and state)."""
        rows = await self._rows("""
            SELECT type, state, count(*) AS n,
                   count(*) FILTER (WHERE severity = 'critical' AND due_at < :now
                                      AND state IN ('NEW','ASSEMBLING','AWAITING_DECISION','ESCALATED')) AS late
              FROM card.card WHERE state = ANY(:open) GROUP BY type, state ORDER BY type, state""",
            now=now, open=OPEN)
        return sum(r.n for r in rows), sum(r.late for r in rows), [(r.type, r.state, int(r.n)) for r in rows]

    async def by_day(self, lo: datetime, hi: datetime) -> dict[date, Figures]:
        days: dict[date, Figures] = {}

        def day(d: date) -> Figures:
            return days.setdefault(d, Figures())

        for r in await self._rows("""SELECT (created_at AT TIME ZONE 'UTC')::date AS k, count(*) AS n FROM card.card
                                       WHERE created_at >= :lo AND created_at < :hi GROUP BY 1""", lo=lo, hi=hi):
            day(r.k).created = int(r.n)
        for r in await self._rows(_EVENTS.format(group=BY_DAY["event"]), lo=lo, hi=hi):
            d = day(r.k)
            d.decided, d.writebacks_ok, d.writebacks_failed = int(r.decided), int(r.ok), int(r.failed)
        for r in await self._rows(_BREACHES.format(group=BY_DAY["card"]), lo=lo, hi=hi):
            day(r.k).breaches = int(r.n)
        for r in await self._rows(_GATES.format(group=BY_DAY["gate"]), lo=lo, hi=hi):
            d = day(r.k)
            d.gate1_runs, d.gate1_monitor, d.gate_p95_ms = int(r.g1), int(r.monitor), float(r.p95)
        for r in await self._rows(_FIELDS.format(group=BY_DAY["field"]), lo=lo, hi=hi):
            d = day(r.k)
            d.fields, d.fields_low = int(r.total), int(r.low)
        return days

    async def period(self, lo: datetime, hi: datetime) -> Figures:
        """Totals over a period. Ratios and the p95 are computed over the period, not averaged over days."""
        f = Figures()
        for r in await self._rows(_EVENTS.format(group=ALL), lo=lo, hi=hi):
            f.decided, f.writebacks_ok, f.writebacks_failed = int(r.decided), int(r.ok), int(r.failed)
        for r in await self._rows(_GATES.format(group=ALL), lo=lo, hi=hi):
            f.gate1_runs, f.gate1_monitor = int(r.g1), int(r.monitor)
            f.gate_p95_ms = float(r.p95) if r.p95 is not None else None
        for r in await self._rows(_BREACHES.format(group="c.owner_team"), lo=lo, hi=hi):
            f.breaches_by_team[r.k] = int(r.n)
        f.breaches = sum(f.breaches_by_team.values())
        for r in await self._rows(_FIELDS.format(group="coalesce(s.bank, 'Unknown bank')"), lo=lo, hi=hi):
            f.low_by_bank[r.k] = (int(r.total), int(r.low))
        f.fields = sum(total for total, _ in f.low_by_bank.values())
        f.fields_low = sum(low for _, low in f.low_by_bank.values())
        f.gate_outcomes = [(r.ruleset_key, r.outcome, int(r.n)) for r in await self._rows("""
            SELECT ruleset_key, outcome, count(*) AS n FROM rules.gate_run
             WHERE evaluated_at >= :lo AND evaluated_at < :hi GROUP BY 1, 2 ORDER BY 1, 2""", lo=lo, hi=hi)]
        return f

    async def llm_tokens(self, since: datetime) -> tuple[int, int]:
        """Model tokens (input, output) used since a moment: gate runs and card recommendations."""
        rows = await self._rows("""
            SELECT coalesce(sum((llm->>'inputTokens')::bigint), 0) AS i,
                   coalesce(sum((llm->>'outputTokens')::bigint), 0) AS o
              FROM (SELECT llm FROM rules.gate_run WHERE evaluated_at >= :since AND llm ? 'inputTokens'
                    UNION ALL
                    SELECT detail->'llm' FROM card.card_evidence
                     WHERE created_at >= :since AND detail->'llm' ? 'inputTokens') AS used""", since=since)
        return int(rows[0].i), int(rows[0].o)
