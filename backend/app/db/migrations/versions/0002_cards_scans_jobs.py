"""Cards, scans and the job queue (slice 2: UC4 and UC5).

Revision ID: 0002_cards_scans_jobs
Revises: 0001_platform_baseline
Created: 2026-10-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_cards_scans_jobs"
down_revision: str | Sequence[str] | None = "0001_platform_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.TIMESTAMP(timezone=True)
CARD_STATES = (
    "'NEW','ASSEMBLING','AWAITING_DECISION','ESCALATED','APPROVED','REJECTED',"
    "'WRITING_BACK','WRITEBACK_FAILED','REVERSED','CLOSED'"
)


def upgrade() -> None:
    op.create_table(
        "job",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", TS, nullable=False),
        sa.Column("lease_until", TS, nullable=True),
        sa.Column("leased_by", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("finished_at", TS, nullable=True),
        sa.PrimaryKeyConstraint("job_id", name="pk_job"),
        sa.UniqueConstraint("dedupe_key", name="uq_job_dedupe_key"),
        sa.CheckConstraint("status IN ('QUEUED','RUNNING','DONE','FAILED')", name="ck_job_status"),
        schema="ops",
    )
    # The lease query reads only due work.
    op.create_index("ix_job_due", "job", ["run_after"], schema="ops",
                    postgresql_where=sa.text("status IN ('QUEUED','RUNNING')"))

    op.create_table(
        "scan",
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("ruleset_key", sa.Text(), nullable=False),
        sa.Column("layer", sa.Text(), nullable=False),
        sa.Column("batch_date", sa.Date(), nullable=True),
        sa.Column("scan_window", sa.Text(), nullable=True),
        sa.Column("max_new_findings", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("findings_total", sa.Integer(), nullable=True),
        sa.Column("findings_new", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("started_at", TS, nullable=True),
        sa.Column("finished_at", TS, nullable=True),
        sa.PrimaryKeyConstraint("scan_id", name="pk_scan"),
        sa.CheckConstraint("layer IN ('bronze','silver','gold')", name="ck_scan_layer"),
        sa.CheckConstraint("status IN ('queued','running','completed','failed')", name="ck_scan_status"),
        schema="rules",
    )
    op.create_table(
        "finding",
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=False),
        sa.Column("policy_id", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False),
        sa.Column("is_new", sa.Boolean(), nullable=False),
        sa.Column("new_rank", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("finding_id", name="pk_finding"),
        sa.ForeignKeyConstraint(["scan_id"], ["rules.scan.scan_id"], name="fk_finding_scan_id_scan"),
        schema="rules",
    )
    op.create_index("ix_finding_new", "finding", ["scan_id", "new_rank"], schema="rules",
                    postgresql_where=sa.text("is_new"))

    op.create_table(
        "card",
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("type_version", sa.Integer(), nullable=False),
        sa.Column("use_case", sa.Text(), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("owner_team", sa.Text(), nullable=False),
        sa.Column("owner_oid", sa.Uuid(), nullable=True),
        sa.Column("maker_oid", sa.Uuid(), nullable=True),
        sa.Column("due_at", TS, nullable=False),
        sa.Column("blocks_subject", sa.Boolean(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("gate_run_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("return_count", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("card_id", name="pk_card"),
        sa.UniqueConstraint("idempotency_key", name="uq_card_idempotency_key"),
        sa.CheckConstraint(f"state IN ({CARD_STATES})", name="ck_card_state"),
        sa.CheckConstraint("severity IN ('low','medium','high','critical')", name="ck_card_severity"),
        schema="card",
    )
    # Inbox by team and due date, and the SLA sweep over open cards (LLD, Core DDL).
    op.create_index("ix_card_open_by_team", "card", ["owner_team", "due_at"], schema="card",
                    postgresql_where=sa.text("state <> 'CLOSED'"))
    op.create_index("ix_card_subject", "card", ["subject_type", "subject_id"], schema="card")
    op.create_index("ix_card_due", "card", ["due_at"], schema="card",
                    postgresql_where=sa.text("state IN ('ASSEMBLING','AWAITING_DECISION','ESCALATED')"))

    op.create_table(
        "card_event",
        sa.Column("event_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("from_state", sa.Text(), nullable=True),
        sa.Column("to_state", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False),
        sa.Column("at", TS, nullable=False),
        sa.PrimaryKeyConstraint("event_id", name="pk_card_event"),
        sa.ForeignKeyConstraint(["card_id"], ["card.card.card_id"], name="fk_card_event_card_id_card"),
        schema="card",
    )
    op.create_index("ix_card_event_card", "card_event", ["card_id", "event_id"], schema="card")

    op.create_table(
        "card_evidence",
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("ref", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("evidence_id", name="pk_card_evidence"),
        sa.ForeignKeyConstraint(["card_id"], ["card.card.card_id"], name="fk_card_evidence_card_id_card"),
        schema="card",
    )
    op.create_index("ix_card_evidence_card", "card_evidence", ["card_id"], schema="card")


def downgrade() -> None:
    op.drop_table("card_evidence", schema="card")
    op.drop_table("card_event", schema="card")
    op.drop_table("card", schema="card")
    op.drop_table("finding", schema="rules")
    op.drop_table("scan", schema="rules")
    op.drop_table("job", schema="ops")
