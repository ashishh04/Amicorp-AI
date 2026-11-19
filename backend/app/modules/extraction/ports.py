"""What extraction needs from outside: the extraction service (layout, OCR, fields and confidence on the GPU
node), and n8n's callback webhook. Adapters live in app/integrations; the worker wires them in."""
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True)
class ExtractionRequest:
    document_id: uuid.UUID
    object_key: str
    profile: str  # bank-statement | nav-statement
    received_at: datetime


@dataclass(frozen=True)
class ExtractedLine:
    line_no: int
    value_date: date
    description: str
    debit: Decimal | None
    credit: Decimal | None
    balance: Decimal | None
    en_number: str | None
    confidence: dict[str, float]  # per portal field name: valueDate, description, debit, credit, balance, enNumber
    box: dict[str, float]  # {page, top, height}, in % of the page


@dataclass(frozen=True)
class ExtractedStatement:
    model_id: str
    threshold: Decimal  # fields below it are flagged for the Maker
    bank: str
    account_no: str
    account_name: str
    currency: str
    period_from: date
    period_to: date
    opening_balance: Decimal
    closing_balance: Decimal
    pages: int
    references: dict[str, str]  # bankId, accountNo, entity as printed on the statement
    lines: list[ExtractedLine] = field(default_factory=list)


@dataclass(frozen=True)
class ExtractedNav:
    """What extraction reads from a NAV statement (UC3)."""

    model_id: str
    pages: int
    fund_code: str
    fund_name: str
    share_class: str
    currency: str
    valuation_date: date
    nav_per_share: Decimal
    previous_nav_per_share: Decimal
    shares_in_issue: Decimal
    register_shares: Decimal  # the transfer agent's register, for the reconciliation check
    total_nav: Decimal


class Extractor(Protocol):
    async def extract(self, request: ExtractionRequest) -> ExtractedStatement | ExtractedNav:
        """A bank statement for profile bank-statement, a NAV statement for nav-statement."""
        ...


class CallbackSender(Protocol):
    async def send(self, url: str, body: dict[str, Any]) -> None:
        """POST the body to n8n; raise if n8n does not accept it, so the job retries."""
        ...
