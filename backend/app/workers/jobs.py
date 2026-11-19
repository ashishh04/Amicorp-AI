"""The jobs worker: runs queued scans, extractions and their n8n callbacks, card recommendations, evidence
reviews and write-backs, payment holds, and notification deliveries.

    python -m app.workers.jobs

Locally, EMBEDDED_WORKER=true runs the same loop inside the API process instead.

Each job runs in its own unit of work: the job's effects, its audit events and its DONE mark commit
together. A failed job is retried with exponential backoff; when the last attempt fails, the kind's
failure hook decides what people see (a failed scan, a card without a summary).
"""
import asyncio
import os
import socket
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import UnitOfWork, make_engine
from app.integrations import care, extractor, five_series, lake, maas, n8n, teams, writeback
from app.modules.cards import service as cards
from app.modules.cards.ports import EvidenceDraft, WriteBack
from app.modules.extraction import service as extraction
from app.modules.extraction.ports import CallbackSender
from app.modules.gates.schemas import GateRunView
from app.modules.notifications import service as notifications
from app.modules.scans import service as scans
from app.modules.statements import service as statements
from app.modules.transaction_monitoring import service as transactions
from app.modules.transaction_monitoring.ports import PaymentSystem
from app.shared import jobs

log = structlog.get_logger()

Handler = Callable[[UnitOfWork, dict[str, Any]], Awaitable[None]]
FailureHook = Callable[[UnitOfWork, dict[str, Any], str], Awaitable[None]]

ACTOR = "svc:jobs-worker"
LEASE_SECONDS = 300
BATCH = 10

FAILURE_HOOKS: dict[str, FailureHook] = {
    scans.SCAN_JOB: scans.fail_scan_job,
    cards.RECOMMEND_JOB: cards.recommend_failed,
    cards.ASSEMBLE_JOB: cards.recommend_failed,
    cards.REVIEW_JOB: cards.recommend_failed,
    cards.WRITEBACK_JOB: cards.writeback_failed,
    extraction.EXTRACT_JOB: extraction.run_failed,
}


class RoutedWriteBack:
    """An approved outcome goes to its own system of record: a UC2 decision releases or freezes the payment in
    5 Series, an approved NAV is published to Valuefy; everything else goes through the generic writer."""

    def __init__(self, default: WriteBack, payments: PaymentSystem) -> None:
        self._default, self._payments = default, payments

    async def write_back(self, uow: UnitOfWork, card_type: str, subject_id: str, payload: dict[str, Any]) -> str:
        if card_type.startswith("aml."):
            return await transactions.apply_decision(uow, card_type, subject_id, self._payments)
        reference = await self._default.write_back(uow, card_type, subject_id, payload)
        if card_type == "nav.approval":
            await statements.nav_published(uow, subject_id, reference)
        return reference


def build_handlers(settings: Settings, *, callbacks: CallbackSender | None = None) -> dict[str, Handler]:
    """Wire each job kind to its adapters. Services only know their ports. Tests pass their own `callbacks`,
    so no test ever calls a real n8n."""
    source = lake.scan_source(settings)
    recommender = maas.recommender(settings)
    reviewer = maas.evidence_reviewer(settings)
    profiles = care.profiles(settings)
    sender = teams.sender(settings)
    reader = extractor.extractor(settings)
    payments = five_series.payments(settings)
    writer = RoutedWriteBack(writeback.writer(settings), payments)
    to_n8n = callbacks or n8n.WebhookCallbacks(settings.n8n_extraction_webhook_token)

    async def run_scan(uow: UnitOfWork, payload: dict[str, Any]) -> None:
        await scans.run_scan_job(uow, payload, source)

    async def recommend(uow: UnitOfWork, payload: dict[str, Any]) -> None:
        await cards.recommend_job(uow, payload, recommender, scans.finding_evidence)

    async def subject_evidence(
        uow: UnitOfWork, card_type: str, subject_id: str, runs: Sequence[GateRunView]
    ) -> list[EvidenceDraft]:
        # The module that owns the subject describes it: payments for UC2, statements for UC1 and UC3.
        if card_type.startswith("aml."):
            return await transactions.card_evidence(uow, subject_id, runs, profiles)
        return await statements.card_evidence(uow, card_type, subject_id)

    async def assemble(uow: UnitOfWork, payload: dict[str, Any]) -> None:
        await cards.assemble_job(uow, payload, subject_evidence)

    async def review(uow: UnitOfWork, payload: dict[str, Any]) -> None:
        await cards.review_job(uow, payload, reviewer, statements.card_facts)

    async def write_back(uow: UnitOfWork, payload: dict[str, Any]) -> None:
        await cards.writeback_job(uow, payload, writer)

    async def deliver(uow: UnitOfWork, payload: dict[str, Any]) -> None:
        await notifications.deliver_job(uow, payload, sender)

    async def extract(uow: UnitOfWork, payload: dict[str, Any]) -> None:
        await extraction.run_job(uow, payload, reader)

    async def call_back(uow: UnitOfWork, payload: dict[str, Any]) -> None:
        await extraction.callback_job(uow, payload, to_n8n)

    async def hold(uow: UnitOfWork, payload: dict[str, Any]) -> None:
        await transactions.hold_job(uow, payload, payments)

    return {
        scans.SCAN_JOB: run_scan, cards.RECOMMEND_JOB: recommend, cards.ASSEMBLE_JOB: assemble,
        cards.REVIEW_JOB: review, cards.WRITEBACK_JOB: write_back,
        notifications.DELIVER_JOB: deliver, extraction.EXTRACT_JOB: extract, extraction.CALLBACK_JOB: call_back,
        transactions.HOLD_JOB: hold,
    }


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


async def run_due_jobs(
    session_factory: async_sessionmaker[AsyncSession], handlers: dict[str, Handler], *, worker: str
) -> int:
    """Lease and run one batch of due jobs. Returns how many were leased."""
    leased = await jobs.lease(session_factory, worker=worker, limit=BATCH, lease_seconds=LEASE_SECONDS)
    for job in leased:
        await _execute(session_factory, handlers, job, worker)
    return len(leased)


async def _execute(
    session_factory: async_sessionmaker[AsyncSession], handlers: dict[str, Handler], job: jobs.LeasedJob, worker: str
) -> None:
    bound = log.bind(job_id=str(job.job_id), job_kind=job.kind, attempt=job.attempts)
    handler = handlers.get(job.kind)
    try:
        if handler is None:
            raise LookupError(f"No handler for job kind {job.kind!r}")
        async with UnitOfWork(session_factory, actor=ACTOR, correlation_id=f"job:{job.job_id}") as uow:
            await handler(uow, job.payload)
            await jobs.mark_done(uow.session, job.job_id, worker, uow.now)
        bound.info("job.done")
    except Exception as exc:  # noqa: BLE001 - any failure is recorded on the job and retried
        final = handler is None or job.attempts >= job.max_attempts
        await jobs.mark_failed(session_factory, job, f"{type(exc).__name__}: {exc}", final=final)
        bound.warning("job.failed", final=final, error_type=type(exc).__name__)
        hook = FAILURE_HOOKS.get(job.kind)
        if final and hook is not None:
            async with UnitOfWork(session_factory, actor=ACTOR, correlation_id=f"job:{job.job_id}") as uow:
                await hook(uow, job.payload, f"{type(exc).__name__}: {exc}")


async def run_forever(
    session_factory: async_sessionmaker[AsyncSession],
    handlers: dict[str, Handler],
    stop: asyncio.Event,
    *,
    poll_seconds: float = 1.0,
) -> None:
    worker = worker_id()
    log.info("jobs.worker_started", worker=worker)
    while not stop.is_set():
        try:
            leased = await run_due_jobs(session_factory, handlers, worker=worker)
        except Exception:  # noqa: BLE001 - a database blip must not kill the worker
            log.exception("jobs.loop_error")
            leased = 0
        if leased == 0:
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
    log.info("jobs.worker_stopped", worker=worker)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)

    async def _run() -> None:
        engine = make_engine(settings)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await run_forever(session_factory, build_handlers(settings), asyncio.Event())
        finally:
            await engine.dispose()

    with suppress(KeyboardInterrupt):
        # psycopg's async mode needs the selector loop on Windows (the default on Linux).
        asyncio.run(_run(), loop_factory=asyncio.SelectorEventLoop)


if __name__ == "__main__":
    main()
