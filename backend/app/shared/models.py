"""Tables owned by the shared kernel: the idempotency record, the audit trail and the job queue."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Integer, LargeBinary, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Job(Base):
    """Durable background work for the jobs worker, leased with SELECT ... FOR UPDATE SKIP LOCKED."""

    __tablename__ = "job"
    __table_args__ = {"schema": "ops"}

    job_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    dedupe_key: Mapped[str | None] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(Text)  # QUEUED | RUNNING | DONE | FAILED
    attempts: Mapped[int] = mapped_column(Integer)
    max_attempts: Mapped[int] = mapped_column(Integer)
    run_after: Mapped[datetime]
    lease_until: Mapped[datetime | None]
    leased_by: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]


class IdempotencyRecord(Base):
    """One row per (caller, method, path, Idempotency-Key): the stored response for replays."""

    __tablename__ = "idempotency_key"
    __table_args__ = {"schema": "ops"}

    key_hash: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    request_hash: Mapped[bytes] = mapped_column(LargeBinary)
    principal: Mapped[str] = mapped_column(Text)
    route: Mapped[str] = mapped_column(Text)
    http_status: Mapped[int] = mapped_column(Integer)
    response: Mapped[Any] = mapped_column(JSONB)
    created_at: Mapped[datetime]


class AuditEventRow(Base):
    """Append-only and hash-chained; a database trigger rejects UPDATE and DELETE."""

    __tablename__ = "audit_event"
    __table_args__ = {"schema": "audit"}

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    at: Mapped[datetime] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    entity: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    prev_hash: Mapped[bytes] = mapped_column(LargeBinary)
    hash: Mapped[bytes] = mapped_column(LargeBinary)


class ChainHead(Base):
    """The last sequence number and hash of an audit chain; locked as the last step of each commit."""

    __tablename__ = "chain_head"
    __table_args__ = {"schema": "audit"}

    chain_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    last_seq: Mapped[int] = mapped_column(BigInteger)
    last_hash: Mapped[bytes] = mapped_column(LargeBinary)
