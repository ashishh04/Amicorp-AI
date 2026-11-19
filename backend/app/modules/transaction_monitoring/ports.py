"""What transaction monitoring needs from outside: 5 Series (the payment and its hold), CARE (the client's
profile), the screening provider (World-Check One or Amicheck) and the model that reads a payment against the
profile (gate 2). Adapters live in app/integrations; the gates router and the worker wire them in."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class Payment:
    transaction_id: str
    client_id: str
    client_name: str
    entity_key: str  # whose payments aggregate in gate 1's 7-day window
    amount: Decimal
    currency: str
    amount_usd: Decimal
    counterparty_id: str
    counterparty_name: str
    beneficiary_ctry: str  # ISO 3166 alpha-2
    purpose: str
    unusual_flag: bool
    value_date: date


class PaymentSystem(Protocol):
    """5 Series: the payment's details, new payment requests, and holds."""

    async def payment(self, transaction_id: str) -> Payment | None: ...

    async def new_requests(self) -> list[tuple[str, str]]:
        """(transaction ID, source) of payment requests that arrived since the last call."""
        ...

    async def hold(self, transaction_id: str) -> str:
        """Hold the payment; returns 5 Series' reference for the hold."""
        ...

    async def release(self, transaction_id: str, hold_reference: str | None) -> str: ...

    async def freeze(self, transaction_id: str, hold_reference: str | None) -> str: ...


@dataclass(frozen=True)
class ClientProfile:
    client_id: str
    name: str
    countries: tuple[str, ...]  # where the client is expected to send money
    max_amount_usd: Decimal  # the largest single payment the profile expects
    purposes: tuple[str, ...]
    risk_score: int  # 0 to 100, CARE's client risk rating
    pep: bool


class ClientProfiles(Protocol):
    """CARE: the client's KYC profile."""

    async def profile(self, client_id: str) -> ClientProfile | None: ...


class ScreeningUnavailable(Exception):
    """The screening provider did not answer. The gate fails closed: the payment stays held."""


@dataclass(frozen=True)
class ScreeningResult:
    hit: bool
    score: int  # 0 to 100
    reference: str  # the provider's case reference, kept with the gate run
    matched_name: str | None = None


class Screening(Protocol):
    async def screen(self, name: str, country: str) -> ScreeningResult: ...


@dataclass(frozen=True)
class ProfileJudgement:
    verdict: Literal["match", "mismatch", "uncertain"]
    reason: str
    llm: dict[str, Any] | None = None  # model, prompt and cost, kept with the gate run


class ProfileInterpreter(Protocol):
    """Gate 2: does the payment fit what the client's profile says the client does?"""

    async def judge(self, payment: Payment, profile: ClientProfile) -> ProfileJudgement: ...
