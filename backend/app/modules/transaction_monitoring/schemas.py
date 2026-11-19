"""Pydantic models for transaction monitoring (n8n UC2: intake, claim, enrichment, filing)."""
import uuid
from typing import Literal

from pydantic import AwareDatetime, Field

from app.shared.schemas import ApiModel

TransactionId = str  # validated by the pattern on each field
TX_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$"


class TransactionIntake(ApiModel):
    transaction_id: TransactionId = Field(pattern=TX_PATTERN)
    source: str = Field(default="realtime", min_length=1, max_length=32)
    received_at: AwareDatetime


class TransactionRegistered(ApiModel):
    transaction_id: str
    created: bool
    state: str


class ClaimRequest(ApiModel):
    status: Literal["new"] = "new"
    limit: int = Field(default=50, ge=1, le=200)
    lease_seconds: int = Field(default=600, ge=30, le=3600)


class ClaimedRequest(ApiModel):
    transaction_id: str
    source: str


class ClaimPage(ApiModel):
    items: list[ClaimedRequest]


class EnrichRequest(ApiModel):
    transaction_id: TransactionId = Field(pattern=TX_PATTERN)
    source: str | None = Field(default=None, max_length=32)


class EnrichedTransaction(ApiModel):
    transaction_id: str
    state: str
    client_id: str
    client_name: str
    amount: float
    currency: str
    amount_usd: float
    counterparty_name: str
    beneficiary_ctry: str


class FileRequest(ApiModel):
    gate_run_id: uuid.UUID
    outcome: str = Field(min_length=1, max_length=64)


class TransactionFiled(ApiModel):
    transaction_id: str
    state: Literal["FILED"]
