"""Portal core and UC1: users, lookups, statements, extraction jobs, rulesets and gate runs.

Revision ID: 0003_portal_uc1
Revises: 0002_cards_scans_jobs
Created: 2026-10-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_portal_uc1"
down_revision: str | Sequence[str] | None = "0002_cards_scans_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.TIMESTAMP(timezone=True)
TEXTS = postgresql.ARRAY(sa.Text())
MONEY = sa.Numeric(18, 2)

RULESET_VERSION_GUARD = """
CREATE FUNCTION rules.forbid_changing_approved_version() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status IN ('approved', 'superseded') AND (
       NEW.rules IS DISTINCT FROM OLD.rules OR NEW.body_sha256 IS DISTINCT FROM OLD.body_sha256
       OR NEW.effective_from IS DISTINCT FROM OLD.effective_from OR NEW.approved_by IS DISTINCT FROM OLD.approved_by)
  THEN
    RAISE EXCEPTION 'An approved ruleset version cannot change; cut a new version instead';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER ruleset_version_immutable
  BEFORE UPDATE ON rules.ruleset_version
  FOR EACH ROW EXECUTE FUNCTION rules.forbid_changing_approved_version();
"""


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("calendar", sa.Text(), nullable=False),
        sa.Column("roles", TEXTS, nullable=False),
        sa.Column("teams", TEXTS, nullable=False),
        sa.Column("data_scope", TEXTS, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("user_id", name="pk_app_user"),
        sa.CheckConstraint("calendar IN ('HK','EU')", name="ck_app_user_calendar"),
        schema="ref",
    )
    op.create_table(
        "en_number",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_en_number"),
        schema="ref",
    )
    op.create_table(
        "bank",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("bic", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("name", name="pk_bank"),
        schema="ref",
    )

    op.create_table(
        "statement",
        sa.Column("statement_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("received_at", TS, nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("bank", sa.Text(), nullable=True),
        sa.Column("account_no", sa.Text(), nullable=True),
        sa.Column("account_name", sa.Text(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("period_from", sa.Date(), nullable=True),
        sa.Column("period_to", sa.Date(), nullable=True),
        sa.Column("opening_balance", MONEY, nullable=True),
        sa.Column("closing_balance", MONEY, nullable=True),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("extraction_job_id", sa.Uuid(), nullable=True),
        sa.Column("model_id", sa.Text(), nullable=True),
        sa.Column("extracted_at", TS, nullable=True),
        sa.Column("threshold", sa.Numeric(4, 3), nullable=True),
        sa.Column("refs", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("statement_id", name="pk_statement"),
        sa.UniqueConstraint("object_key", name="uq_statement_object_key"),
        sa.CheckConstraint("kind IN ('bank','nav')", name="ck_statement_kind"),
        sa.CheckConstraint(
            "state IN ('REGISTERED','EXTRACTING','IN_REVIEW','SUBMITTED','FAILED')", name="ck_statement_state"
        ),
        schema="stmt",
    )
    op.create_table(
        "statement_line",
        sa.Column("line_id", sa.Uuid(), nullable=False),
        sa.Column("statement_id", sa.Uuid(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("value_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("debit", MONEY, nullable=True),
        sa.Column("credit", MONEY, nullable=True),
        sa.Column("balance", MONEY, nullable=True),
        sa.Column("en_number", sa.Text(), nullable=True),
        sa.Column("confidence", postgresql.JSONB(), nullable=False),
        sa.Column("corrected", TEXTS, nullable=False),
        sa.Column("corrected_by", sa.Uuid(), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", TS, nullable=True),
        sa.Column("box", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("line_id", name="pk_statement_line"),
        sa.UniqueConstraint("statement_id", "line_no", name="uq_statement_line_statement_id"),
        sa.ForeignKeyConstraint(["statement_id"], ["stmt.statement.statement_id"],
                                name="fk_statement_line_statement_id_statement"),
        schema="stmt",
    )

    op.create_table(
        "extraction_job",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("profile", sa.Text(), nullable=False),
        sa.Column("callback_url", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("callback_acked", sa.Boolean(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("finished_at", TS, nullable=True),
        sa.PrimaryKeyConstraint("job_id", name="pk_extraction_job"),
        sa.CheckConstraint("status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')", name="ck_extraction_job_status"),
        schema="ops",
    )
    op.create_index("ix_extraction_job_document", "extraction_job", ["document_id"], schema="ops")

    op.create_table(
        "ruleset",
        sa.Column("ruleset_key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("owner_team", sa.Text(), nullable=False),
        sa.Column("use_case", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("outcomes", TEXTS, nullable=False),
        sa.Column("default_outcome", sa.Text(), nullable=False),
        sa.Column("sample_inputs", postgresql.JSONB(), nullable=False),
        sa.Column("regression_cases", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("ruleset_key", name="pk_ruleset"),
        schema="rules",
    )
    op.create_table(
        "ruleset_version",
        sa.Column("ruleset_key", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("rules", postgresql.JSONB(), nullable=False),
        sa.Column("body_sha256", sa.LargeBinary(), nullable=False),
        sa.Column("effective_from", TS, nullable=True),
        sa.Column("drafted_by", sa.Uuid(), nullable=False),
        sa.Column("drafted_at", TS, nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", TS, nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("ruleset_key", "version", name="pk_ruleset_version"),
        sa.ForeignKeyConstraint(["ruleset_key"], ["rules.ruleset.ruleset_key"],
                                name="fk_ruleset_version_ruleset_key_ruleset"),
        sa.CheckConstraint("status IN ('draft','approved','superseded')", name="ck_ruleset_version_status"),
        sa.CheckConstraint("approved_by IS NULL OR approved_by <> drafted_by", name="ck_ruleset_version_four_eyes"),
        schema="rules",
    )
    op.create_table(
        "gate_run",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("ruleset_key", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.Text(), nullable=False),
        sa.Column("inputs", postgresql.JSONB(), nullable=False),
        sa.Column("matched_rule", sa.Text(), nullable=True),
        sa.Column("matched_desc", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("llm", postgresql.JSONB(), nullable=True),
        sa.Column("screening_ref", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("evaluated_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("run_id", name="pk_gate_run"),
        sa.ForeignKeyConstraint(["ruleset_key", "version"], ["rules.ruleset_version.ruleset_key",
                                                             "rules.ruleset_version.version"],
                                name="fk_gate_run_ruleset_key_ruleset_version"),
        schema="rules",
    )
    op.create_index("ix_gate_run_subject", "gate_run", ["subject_type", "subject_id", "evaluated_at"], schema="rules")
    op.execute(RULESET_VERSION_GUARD)

    op.add_column("card", sa.Column("title", sa.Text(), nullable=False, server_default=""), schema="card")
    op.add_column("card", sa.Column("delegation_chain", postgresql.ARRAY(sa.Uuid()), nullable=False,
                                    server_default=sa.text("'{}'::uuid[]")), schema="card")


def downgrade() -> None:
    op.drop_column("card", "delegation_chain", schema="card")
    op.drop_column("card", "title", schema="card")
    op.execute("DROP TRIGGER IF EXISTS ruleset_version_immutable ON rules.ruleset_version")
    op.execute("DROP FUNCTION IF EXISTS rules.forbid_changing_approved_version()")
    for table, schema in [("gate_run", "rules"), ("ruleset_version", "rules"), ("ruleset", "rules"),
                          ("extraction_job", "ops"), ("statement_line", "stmt"), ("statement", "stmt"),
                          ("bank", "ref"), ("en_number", "ref"), ("app_user", "ref")]:
        op.drop_table(table, schema=schema)
