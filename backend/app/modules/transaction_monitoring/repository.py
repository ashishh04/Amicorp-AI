"""Database access for transaction monitoring."""
from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.transaction_monitoring.models import PaymentRequest, Transaction

NEAR_THRESHOLD = (Decimal("9000"), Decimal("9999.99"))  # structuring: just below USD 10,000


class TransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, transaction_id: str, *, for_update: bool = False) -> Transaction | None:
        statement = select(Transaction).where(Transaction.transaction_id == transaction_id)
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    def add(self, transaction: Transaction) -> None:
        self.session.add(transaction)

    async def window(self, entity_key: str, until: datetime, days: int) -> tuple[Decimal, int]:
        """(USD total, count just below the threshold) of the entity's payments in the `days` up to `until`."""
        low, high = NEAR_THRESHOLD
        result = await self.session.execute(
            select(func.coalesce(func.sum(Transaction.amount_usd), 0),
                   func.count().filter(Transaction.amount_usd.between(low, high)))
            .where(Transaction.entity_key == entity_key, Transaction.received_at <= until,
                   Transaction.received_at > until - timedelta(days=days))
        )
        total, near = result.one()
        return Decimal(total or 0), int(near)

    async def offer_requests(self, items: Sequence[tuple[str, str]], now: datetime) -> None:
        """New payment requests from 5 Series; a request already known keeps its status."""
        if items:
            await self.session.execute(
                insert(PaymentRequest).values([
                    {"transaction_id": tx, "source": source, "status": "new", "created_at": now} for tx, source in items
                ]).on_conflict_do_nothing(index_elements=[PaymentRequest.transaction_id])
            )

    async def lease_requests(self, worker: str, limit: int, lease_seconds: int, now: datetime) -> list[tuple[str, str]]:
        """Claim up to `limit` new (or lease-expired) requests in one statement; overlapping polls skip them."""
        result = await self.session.execute(text("""
            UPDATE txn.payment_request
               SET status = 'claimed', claimed_by = :worker, lease_until = :until
             WHERE transaction_id IN (
                   SELECT transaction_id FROM txn.payment_request
                    WHERE status = 'new' OR (status = 'claimed' AND lease_until < :now)
                    ORDER BY created_at
                    LIMIT :limit
                      FOR UPDATE SKIP LOCKED)
         RETURNING transaction_id, source, created_at
        """), {"worker": worker, "until": now + timedelta(seconds=lease_seconds), "now": now, "limit": limit})
        # RETURNING keeps no order; the poller gets the oldest request first, as the queue intends.
        return [(row.transaction_id, row.source) for row in sorted(result, key=lambda r: r.created_at)]

    async def finish_request(self, transaction_id: str) -> None:
        request = await self.session.get(PaymentRequest, transaction_id)
        if request is not None:
            request.status, request.lease_until = "done", None

    async def requeue_request(self, transaction_id: str, source: str, now: datetime) -> None:
        await self.session.execute(
            insert(PaymentRequest).values(transaction_id=transaction_id, source=source, status="new", created_at=now)
            .on_conflict_do_update(index_elements=[PaymentRequest.transaction_id],
                                   set_={"status": "new", "lease_until": None, "claimed_by": None})
        )

    async def stuck(self, older_than: datetime) -> Sequence[Transaction]:
        """Registered but never enriched: the workflow stopped between intake and gate 1."""
        result = await self.session.execute(
            select(Transaction).where(Transaction.state == "RECEIVED", Transaction.received_at < older_than)
        )
        return result.scalars().all()
