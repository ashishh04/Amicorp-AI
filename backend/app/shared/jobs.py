"""The job queue: durable background work in PostgreSQL (blueprint sections 3 and 8).

A request never does slow or external work itself. It enqueues a job in the same transaction as its
state change, so the job exists if and only if the change committed. The jobs worker leases due jobs
with SELECT ... FOR UPDATE SKIP LOCKED: any number of workers can share the queue without a broker,
and a crashed worker's jobs return to the queue when their lease expires.
"""
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.models import Job

DEFAULT_MAX_ATTEMPTS = 5
MAX_BACKOFF_SECONDS = 900


@dataclass(frozen=True)
class LeasedJob:
    job_id: uuid.UUID
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


async def enqueue(
    session: AsyncSession,
    kind: str,
    payload: dict[str, Any],
    *,
    now: datetime,
    dedupe_key: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> None:
    """Add a job inside the caller's transaction. A job with the same dedupe_key is never added twice.

    It is due from the database's clock, the clock lease() compares against, so an API server whose clock
    runs ahead of the database's cannot leave a fresh job looking "not yet due"."""
    statement = insert(Job).values(
        job_id=uuid.uuid4(), kind=kind, payload=payload, dedupe_key=dedupe_key, status="QUEUED",
        attempts=0, max_attempts=max_attempts, run_after=func.now(), created_at=now,
    )
    await session.execute(statement.on_conflict_do_nothing(index_elements=[Job.dedupe_key]))


_LEASE = text("""
    UPDATE ops.job
       SET status = 'RUNNING', attempts = attempts + 1, leased_by = :worker,
           lease_until = now() + make_interval(secs => :lease_seconds)
     WHERE job_id IN (
           SELECT job_id FROM ops.job
            WHERE (status = 'QUEUED' AND run_after <= now())
               OR (status = 'RUNNING' AND lease_until < now())
            ORDER BY run_after
            LIMIT :limit
              FOR UPDATE SKIP LOCKED)
 RETURNING job_id, kind, payload, attempts, max_attempts, run_after, created_at
""")


async def lease(
    session_factory: async_sessionmaker[AsyncSession], *, worker: str, limit: int, lease_seconds: int
) -> list[LeasedJob]:
    """Claim up to `limit` due jobs in one statement; no other worker can see them until the lease ends."""
    async with session_factory() as session, session.begin():
        rows = await session.execute(_LEASE, {"worker": worker, "limit": limit, "lease_seconds": lease_seconds})
        # RETURNING keeps no order; the batch runs oldest first, as the queue intends.
        return [LeasedJob(r.job_id, r.kind, r.payload, r.attempts, r.max_attempts)
                for r in sorted(rows, key=lambda r: (r.run_after, r.created_at))]


async def mark_done(session: AsyncSession, job_id: uuid.UUID, worker: str, now: datetime) -> None:
    """Call inside the handler's transaction, so the job's effects and its completion commit together."""
    await session.execute(
        update(Job).where(Job.job_id == job_id, Job.leased_by == worker)
        .values(status="DONE", finished_at=now, lease_until=None, last_error=None)
    )


async def mark_failed(
    session_factory: async_sessionmaker[AsyncSession], job: LeasedJob, error: str, *, final: bool
) -> None:
    """Retry later with exponential backoff (2, 4, 8 ... seconds, capped), or stop for good when final."""
    now = datetime.now(UTC)
    backoff = timedelta(seconds=min(2**job.attempts, MAX_BACKOFF_SECONDS))
    async with session_factory() as session, session.begin():
        await session.execute(
            update(Job).where(Job.job_id == job.job_id).values(
                status="FAILED" if final else "QUEUED",
                run_after=func.now() if final else func.now() + backoff,  # the database's clock, as in enqueue
                lease_until=None,
                last_error=error[:2000],
                finished_at=now if final else None,
            )
        )
