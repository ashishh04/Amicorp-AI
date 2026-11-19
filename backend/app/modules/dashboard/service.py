"""The KPI summary (portal contract: GET /v1/dashboard/summary; HLD service indicators). No HTTP or SQL here.

Each KPI over the range, per day (the tiles' trend lines), and over the previous period of the same length
(the change indicators). Ratios and the p95 are computed over each period, never averaged across days. A
day with nothing to measure shows the period's value, so a quiet day does not look like a drop to zero.
"""
from datetime import UTC, date, datetime, timedelta

from app.db.session import UnitOfWork
from app.modules.dashboard.repository import DashboardRepository, Figures
from app.modules.dashboard.schemas import (
    DailyCount,
    FormatPct,
    GateOutcomeCount,
    KpiSeries,
    KpiSummary,
    KpiValues,
    LlmTokens,
    TeamCount,
    TypeStateCount,
)


def _pct(part: int, whole: int, empty: float) -> float:
    return round(part * 100 / whole, 1) if whole else empty


def _rates(f: Figures) -> tuple[float, float, float, float]:
    """(write-back success %, UC2 hold rate %, gate latency p95 ms, low-confidence field %)."""
    return (
        _pct(f.writebacks_ok, f.writebacks_ok + f.writebacks_failed, 100.0),
        _pct(f.gate1_monitor, f.gate1_runs, 0.0),
        round(f.gate_p95_ms or 0.0),
        _pct(f.fields_low, f.fields, 0.0),
    )


async def summary(uow: UnitOfWork, days: int, token_budget: tuple[int, int]) -> KpiSummary:
    async with uow:
        now = uow.now
        today = now.astimezone(UTC).date()
        start = today - timedelta(days=days - 1)
        lo, hi = _midnight(start), _midnight(today + timedelta(days=1))
        prev_lo = _midnight(start - timedelta(days=days))
        repo = DashboardRepository(uow.session)
        open_cards, critical_late, by_type_state = await repo.open_now(now)
        per_day = await repo.by_day(lo, hi)
        current = await repo.period(lo, min(hi, now))
        previous = await repo.period(prev_lo, lo)
        used_in, used_out = await repo.llm_tokens(_midnight(today.replace(day=1)))

    dates = [start + timedelta(days=i) for i in range(days)]
    figures = [per_day.get(d, Figures()) for d in dates]
    rates_now, rates_before = _rates(current), _rates(previous)

    # Open cards per day: walk back from today's backlog through each day's new and decided cards.
    open_series, backlog = [0.0] * days, open_cards
    for i in range(days - 1, -1, -1):
        open_series[i] = float(max(0, backlog))
        backlog = backlog - figures[i].created + figures[i].decided

    def daily_rate(f: Figures, index: int) -> float:
        measured = {0: f.writebacks_ok + f.writebacks_failed, 1: f.gate1_runs, 2: f.gate1_runs, 3: f.fields}[index]
        return _rates(f)[index] if measured else rates_now[index]

    return KpiSummary(
        range_days=days, open_cards=open_cards, critical_past_due=critical_late, sla_breaches=current.breaches,
        decisions=sum(f.decided for f in figures), writeback_success_pct=rates_now[0], uc2_hold_rate_pct=rates_now[1],
        gate_latency_p95_ms=rates_now[2], low_confidence_field_pct=rates_now[3],
        daily=[DailyCount(date=d.isoformat(), created=f.created, decided=f.decided, breaches=f.breaches)
               for d, f in zip(dates, figures, strict=True)],
        open_by_type_state=[TypeStateCount(type=t, state=s, count=n) for t, s, n in by_type_state],
        gate_outcomes=[GateOutcomeCount(ruleset_key=k, outcome=o, count=n) for k, o, n in current.gate_outcomes],
        low_confidence_by_format=[FormatPct(format=f"{bank} PDF", pct=_pct(low, total, 0.0))
                                  for bank, (total, low) in sorted(current.low_by_bank.items())],
        breaches_by_team=[TeamCount(team=t, count=n) for t, n in sorted(current.breaches_by_team.items())],
        llm_tokens=LlmTokens(used_in=used_in, used_out=used_out, budget_in=token_budget[0],
                             budget_out=token_budget[1]),
        series=KpiSeries(
            open_cards=open_series,
            critical_past_due=[0.0] * (days - 1) + [float(critical_late)],
            sla_breaches=[float(f.breaches) for f in figures],
            decisions=[float(f.decided) for f in figures],
            writeback_success_pct=[daily_rate(f, 0) for f in figures],
            uc2_hold_rate_pct=[daily_rate(f, 1) for f in figures],
            gate_latency_p95_ms=[float(round(f.gate_p95_ms)) if f.gate_p95_ms is not None else rates_now[2]
                                 for f in figures],
            low_confidence_field_pct=[daily_rate(f, 3) for f in figures],
        ),
        previous=KpiValues(
            open_cards=float(max(0, backlog)), critical_past_due=0.0, sla_breaches=previous.breaches,
            decisions=previous.decided, writeback_success_pct=rates_before[0], uc2_hold_rate_pct=rates_before[1],
            gate_latency_p95_ms=rates_before[2], low_confidence_field_pct=rates_before[3],
        ),
    )


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)
