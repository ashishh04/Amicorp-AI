"""SQLAlchemy models for transaction monitoring (UC2)."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

Money = Numeric(18, 2)


class Transaction(Base):
    """A payment under AML monitoring: registered at intake, enriched from 5 Series and CARE, then gated.

    state: RECEIVED -> ENRICHED -> FILED (gate 1 below threshold) or MONITORING (a card decides), then CLEARED
    (released after an Approve) or FROZEN (the MLRO confirmed the escalation). hold_state mirrors the hold in
    5 Series: a payment under monitoring is held until a decision releases or freezes it.
    """

    __tablename__ = "transaction"
    __table_args__ = {"schema": "txn"}

    transaction_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime]
    enriched_at: Mapped[datetime | None]
    client_id: Mapped[str | None] = mapped_column(Text)
    client_name: Mapped[str | None] = mapped_column(Text)
    entity_key: Mapped[str | None] = mapped_column(Text)  # whose payments aggregate in the 7-day window
    amount: Mapped[Decimal | None] = mapped_column(Money)
    currency: Mapped[str | None] = mapped_column(Text)
    amount_usd: Mapped[Decimal | None] = mapped_column(Money)
    counterparty_id: Mapped[str | None] = mapped_column(Text)
    counterparty_name: Mapped[str | None] = mapped_column(Text)
    beneficiary_ctry: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str | None] = mapped_column(Text)
    unusual_flag: Mapped[bool]
    value_date: Mapped[date | None]
    hold_state: Mapped[str] = mapped_column(Text)  # none | held | released | frozen
    hold_reference: Mapped[str | None] = mapped_column(Text)
    filed_gate_run_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class PaymentRequest(Base):
    """A new payment request seen in 5 Series, waiting for the UC2 poller (POST /v1/payment-requests/claim)."""

    __tablename__ = "payment_request"
    __table_args__ = {"schema": "txn"}

    transaction_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)  # new | claimed | done
    lease_until: Mapped[datetime | None]
    claimed_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]
