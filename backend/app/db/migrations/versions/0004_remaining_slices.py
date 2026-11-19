"""Live events, AML reference data, UC2 transactions, UC3 NAV details and the stuck-item sweeper.

Revision ID: 0004_remaining_slices
Revises: 0003_portal_uc1
Created: 2026-10-30
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_remaining_slices"
down_revision: str | Sequence[str] | None = "0003_portal_uc1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.TIMESTAMP(timezone=True)
MONEY = sa.Numeric(18, 2)


def upgrade() -> None:
    # Live events (SSE): an outbox written in the same transaction as the change it reports.
    op.create_table(
        "event_log",
        sa.Column("event_id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("card_type", sa.Text(), nullable=True),
        sa.Column("team", sa.Text(), nullable=True),
        sa.Column("owner_oid", sa.Uuid(), nullable=True),
        sa.Column("at", TS, nullable=False),
        sa.PrimaryKeyConstraint("event_id", name="pk_event_log"),
        schema="ops",
    )
    op.create_index("ix_event_log_at", "event_log", ["at"], schema="ops")

    # Stuck-item sweeper: how often each item was re-driven, and when it was escalated.
    op.create_table(
        "redrive",
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("item_id", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_redriven_at", TS, nullable=False),
        sa.Column("escalated_at", TS, nullable=True),
        sa.PrimaryKeyConstraint("scope", "item_id", name="pk_redrive"),
        schema="ops",
    )

    # Reference data the AML rules read (inList, countryRisk) and the NAV tolerances per fund.
    op.create_table(
        "named_list",
        sa.Column("list_name", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("list_name", "value", name="pk_named_list"),
        schema="ref",
    )
    op.create_table(
        "country_risk",
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column("risk", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("country", name="pk_country_risk"),
        sa.CheckConstraint("risk IN ('high','medium','low')", name="ck_country_risk_risk"),
        schema="ref",
    )
    op.create_table(
        "fund_template",
        sa.Column("fund_code", sa.Text(), nullable=False),
        sa.Column("share_class", sa.Text(), nullable=False),
        sa.Column("fund_name", sa.Text(), nullable=False),
        sa.Column("tolerance_pct", sa.Numeric(6, 3), nullable=False),
        sa.PrimaryKeyConstraint("fund_code", "share_class", name="pk_fund_template"),
        schema="ref",
    )

    # UC2: payments under AML monitoring, and the 5 Series payment requests the poller claims.
    op.execute("CREATE SCHEMA IF NOT EXISTS txn")
    op.create_table(
        "transaction",
        sa.Column("transaction_id", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("received_at", TS, nullable=False),
        sa.Column("enriched_at", TS, nullable=True),
        sa.Column("client_id", sa.Text(), nullable=True),
        sa.Column("client_name", sa.Text(), nullable=True),
        sa.Column("entity_key", sa.Text(), nullable=True),
        sa.Column("amount", MONEY, nullable=True),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("amount_usd", MONEY, nullable=True),
        sa.Column("counterparty_id", sa.Text(), nullable=True),
        sa.Column("counterparty_name", sa.Text(), nullable=True),
        sa.Column("beneficiary_ctry", sa.Text(), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("unusual_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("hold_state", sa.Text(), nullable=False, server_default="none"),
        sa.Column("hold_reference", sa.Text(), nullable=True),
        sa.Column("filed_gate_run_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("transaction_id", name="pk_transaction"),
        sa.CheckConstraint("state IN ('RECEIVED','ENRICHED','FILED','MONITORING','CLEARED','FROZEN')",
                           name="ck_transaction_state"),
        sa.CheckConstraint("hold_state IN ('none','held','released','frozen')", name="ck_transaction_hold_state"),
        schema="txn",
    )
    op.create_index("ix_transaction_entity_received", "transaction", ["entity_key", "received_at"], schema="txn")
    op.create_table(
        "payment_request",
        sa.Column("transaction_id", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("lease_until", TS, nullable=True),
        sa.Column("claimed_by", sa.Text(), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("transaction_id", name="pk_payment_request"),
        sa.CheckConstraint("status IN ('new','claimed','done')", name="ck_payment_request_status"),
        schema="txn",
    )

    # UC3: what extraction reads from a NAV statement (stmt.statement holds the document and its state).
    op.create_table(
        "nav_detail",
        sa.Column("statement_id", sa.Uuid(), nullable=False),
        sa.Column("fund_code", sa.Text(), nullable=False),
        sa.Column("fund_name", sa.Text(), nullable=False),
        sa.Column("share_class", sa.Text(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("valuation_date", sa.Date(), nullable=False),
        sa.Column("nav_per_share", sa.Numeric(18, 6), nullable=False),
        sa.Column("previous_nav_per_share", sa.Numeric(18, 6), nullable=False),
        sa.Column("shares_in_issue", sa.Numeric(20, 4), nullable=False),
        sa.Column("register_shares", sa.Numeric(20, 4), nullable=False),
        sa.Column("total_nav", MONEY, nullable=False),
        sa.PrimaryKeyConstraint("statement_id", name="pk_nav_detail"),
        sa.ForeignKeyConstraint(["statement_id"], ["stmt.statement.statement_id"],
                                name="fk_nav_detail_statement_id_statement"),
        schema="stmt",
    )


def downgrade() -> None:
    op.drop_table("nav_detail", schema="stmt")
    op.drop_table("payment_request", schema="txn")
    op.drop_table("transaction", schema="txn")
    op.execute("DROP SCHEMA IF EXISTS txn")
    for table in ("fund_template", "country_risk", "named_list"):
        op.drop_table(table, schema="ref")
    op.drop_table("redrive", schema="ops")
    op.drop_table("event_log", schema="ops")
