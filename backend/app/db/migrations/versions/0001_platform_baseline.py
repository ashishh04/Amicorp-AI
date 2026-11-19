"""Platform baseline: schemas, idempotency record, incidents, notifications and the audit trail.

Revision ID: 0001_platform_baseline
Revises:
Created: 2026-10-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_platform_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMAS = ("card", "rules", "audit", "stmt", "ref", "ops")

AUDIT_DDL = """
CREATE TABLE audit.chain_head (
  chain_id  smallint PRIMARY KEY,
  last_seq  bigint   NOT NULL,
  last_hash bytea    NOT NULL
);
INSERT INTO audit.chain_head (chain_id, last_seq, last_hash) VALUES (0, 0, decode(repeat('00', 32), 'hex'));

CREATE TABLE audit.audit_event (
  seq            bigint      NOT NULL,
  at             timestamptz NOT NULL,
  actor          text        NOT NULL,
  action         text        NOT NULL,
  entity         text        NOT NULL,
  entity_id      text        NOT NULL,
  correlation_id text,
  payload        jsonb       NOT NULL,
  prev_hash      bytea       NOT NULL,
  hash           bytea       NOT NULL,
  CONSTRAINT pk_audit_event PRIMARY KEY (seq, at)
) PARTITION BY RANGE (at);

-- Safety net only: monthly partitions are created months ahead, so this stays empty.
CREATE TABLE audit.audit_event_default PARTITION OF audit.audit_event DEFAULT;

CREATE INDEX ix_audit_event_entity ON audit.audit_event (entity, entity_id, at);
CREATE INDEX ix_audit_event_actor  ON audit.audit_event (actor, at);

-- Creates the monthly partitions from the current month to months_ahead months later.
CREATE FUNCTION audit.ensure_partitions(months_ahead int) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
  first_month date := date_trunc('month', now() AT TIME ZONE 'UTC')::date;
  m_start date;
  m_end   date;
  part    text;
BEGIN
  FOR i IN 0..months_ahead LOOP
    m_start := (first_month + make_interval(months => i))::date;
    m_end   := (first_month + make_interval(months => i + 1))::date;
    part    := format('audit_event_%s', to_char(m_start, 'YYYY_MM'));
    IF to_regclass(format('audit.%I', part)) IS NULL THEN
      EXECUTE format(
        'CREATE TABLE audit.%I PARTITION OF audit.audit_event FOR VALUES FROM (%L) TO (%L)',
        part, m_start::timestamp AT TIME ZONE 'UTC', m_end::timestamp AT TIME ZONE 'UTC');
    END IF;
  END LOOP;
END $$;

SELECT audit.ensure_partitions(3);

-- Append-only: even the table owner cannot change or delete an audit row.
CREATE FUNCTION audit.forbid_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit.audit_event is append-only';
END $$;

CREATE TRIGGER audit_event_append_only
  BEFORE UPDATE OR DELETE ON audit.audit_event
  FOR EACH ROW EXECUTE FUNCTION audit.forbid_change();
"""


def upgrade() -> None:
    for schema in SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

    op.create_table(
        "idempotency_key",
        sa.Column("key_hash", sa.LargeBinary(), nullable=False),
        sa.Column("request_hash", sa.LargeBinary(), nullable=False),
        sa.Column("principal", sa.Text(), nullable=False),
        sa.Column("route", sa.Text(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key_hash", name="pk_idempotency_key"),
        schema="ops",
    )
    op.create_index("ix_idempotency_key_created_at", "idempotency_key", ["created_at"], schema="ops")

    op.create_table(
        "incident",
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("incident_key", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("workflow_id", sa.Text(), nullable=False),
        sa.Column("workflow_name", sa.Text(), nullable=True),
        sa.Column("execution_id", sa.Text(), nullable=True),
        sa.Column("execution_url", sa.Text(), nullable=True),
        sa.Column("failed_node", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("opened_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("incident_id", name="pk_incident"),
        sa.UniqueConstraint("incident_key", name="uq_incident_incident_key"),
        sa.CheckConstraint("status IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED')", name="ck_incident_status"),
        schema="ops",
    )
    op.create_index("ix_incident_opened_at", "incident", ["opened_at"], schema="ops")

    op.create_table(
        "notification",
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("audience", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("card_id", sa.Uuid(), nullable=True),
        sa.Column("incident_id", sa.Uuid(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("notification_id", name="pk_notification"),
        sa.CheckConstraint("status IN ('QUEUED', 'SENT', 'FAILED')", name="ck_notification_status"),
        schema="ops",
    )
    # The jobs worker picks queued notifications oldest first.
    op.create_index(
        "ix_notification_queued", "notification", ["created_at"], schema="ops",
        postgresql_where=sa.text("status = 'QUEUED'"),
    )

    op.execute(AUDIT_DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit.audit_event CASCADE")
    op.execute("DROP FUNCTION IF EXISTS audit.forbid_change()")
    op.execute("DROP FUNCTION IF EXISTS audit.ensure_partitions(int)")
    op.execute("DROP TABLE IF EXISTS audit.chain_head")
    op.drop_table("notification", schema="ops")
    op.drop_table("incident", schema="ops")
    op.drop_table("idempotency_key", schema="ops")
    for schema in reversed(SCHEMAS):
        op.execute(f"DROP SCHEMA IF EXISTS {schema}")
