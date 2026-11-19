"""Business rules for transaction monitoring (UC2). No HTTP or SQL here.

The flow (LLD, UC2; n8n README): a payment is registered (webhook) or claimed (5 Series poll), enriched from
5 Series and CARE, then gated. Gate 1 (thresholds) files it or starts monitoring, which holds the payment in
5 Series. Gate 2 (the model reads the payment against the client's profile) and gate 3 (risk and live
screening) feed the card that decides it; an Approve releases the hold, or freezes the payment when the MLRO
confirms an escalation. Every decision on a payment is in the AML domain of the audit trail.

Fail closed throughout: an unknown payment, a missing profile or an unanswered screening never lets a payment
through. The gate either takes its blocking outcome or answers with an error, and n8n raises a hold card.
"""
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import timedelta
from decimal import Decimal
from typing import Any

import structlog

from app.core.errors import NotFound, RuleRefused, ServiceUnavailable
from app.db.session import UnitOfWork
from app.modules.cards.ports import EvidenceDraft, SubjectInfo
from app.modules.gates import service as gates
from app.modules.gates.ports import Resolution, ResolvedInput
from app.modules.gates.schemas import GateRunView
from app.modules.transaction_monitoring.models import Transaction
from app.modules.transaction_monitoring.ports import (
    ClientProfile,
    ClientProfiles,
    Payment,
    PaymentSystem,
    ProfileInterpreter,
    Screening,
    ScreeningUnavailable,
)
from app.modules.transaction_monitoring.repository import TransactionRepository
from app.modules.transaction_monitoring.schemas import (
    ClaimedRequest,
    ClaimPage,
    ClaimRequest,
    EnrichedTransaction,
    EnrichRequest,
    FileRequest,
    TransactionFiled,
    TransactionIntake,
    TransactionRegistered,
)
from app.shared import jobs

log = structlog.get_logger()

HOLD_JOB = "txn.hold"
WINDOW_DAYS = 7
FIVE_SERIES = "5 Series payment"
GATE3 = "aml.gate3-risk"


# ---------------------------------------------------------------- n8n: intake, claim, enrich, file

async def register(uow: UnitOfWork, intake: TransactionIntake) -> TransactionRegistered:
    """Durable intake, idempotent on the transaction ID: a repeat returns the transaction as it is."""
    repo = TransactionRepository(uow.session)
    existing = await repo.get(intake.transaction_id)
    if existing is not None:
        return TransactionRegistered(transaction_id=existing.transaction_id, created=False, state=existing.state)
    repo.add(_new(intake.transaction_id, intake.source, uow, received_at=intake.received_at))
    uow.audit.record("transaction.registered", "transaction", intake.transaction_id, {"source": intake.source},
                     domain="AML")
    return TransactionRegistered(transaction_id=intake.transaction_id, created=True, state="RECEIVED")


async def claim(uow: UnitOfWork, worker: str, req: ClaimRequest, payments: PaymentSystem) -> ClaimPage:
    """Lease new 5 Series payment requests to this poll. Overlapping polls never get the same request."""
    repo = TransactionRepository(uow.session)
    await repo.offer_requests(await payments.new_requests(), uow.now)
    leased = await repo.lease_requests(worker, req.limit, req.lease_seconds, uow.now)
    for transaction_id, source in leased:
        if await repo.get(transaction_id) is None:
            repo.add(_new(transaction_id, source, uow))
    if leased:
        uow.audit.record("payment-requests.claimed", "payment-request", worker, {"count": len(leased)}, domain="AML")
    return ClaimPage(items=[ClaimedRequest(transaction_id=t, source=s) for t, s in leased])


async def enrich(uow: UnitOfWork, req: EnrichRequest, payments: PaymentSystem) -> EnrichedTransaction:
    """Read the payment from 5 Series onto the transaction. Echoes the transaction ID for the next node."""
    payment = await payments.payment(req.transaction_id)
    if payment is None:
        raise NotFound(f"5 Series has no payment {req.transaction_id}.")
    repo = TransactionRepository(uow.session)
    tx = await repo.get(req.transaction_id, for_update=True)
    if tx is None:
        tx = _new(req.transaction_id, req.source or "realtime-poll", uow)
        repo.add(tx)
    tx.client_id, tx.client_name, tx.entity_key = payment.client_id, payment.client_name, payment.entity_key
    tx.amount, tx.currency, tx.amount_usd = payment.amount, payment.currency, payment.amount_usd
    tx.counterparty_id, tx.counterparty_name = payment.counterparty_id, payment.counterparty_name
    tx.beneficiary_ctry, tx.purpose = payment.beneficiary_ctry, payment.purpose
    tx.unusual_flag, tx.value_date = payment.unusual_flag, payment.value_date
    tx.enriched_at, tx.updated_at = uow.now, uow.now
    if tx.state == "RECEIVED":
        tx.state = "ENRICHED"
    await repo.finish_request(req.transaction_id)
    uow.audit.record("transaction.enriched", "transaction", req.transaction_id,
                     {"clientId": payment.client_id, "amountUsd": str(payment.amount_usd)}, domain="AML")
    return EnrichedTransaction(
        transaction_id=tx.transaction_id, state=tx.state, client_id=payment.client_id,
        client_name=payment.client_name, amount=float(payment.amount), currency=payment.currency,
        amount_usd=float(payment.amount_usd), counterparty_name=payment.counterparty_name,
        beneficiary_ctry=payment.beneficiary_ctry,
    )


async def file_transaction(uow: UnitOfWork, transaction_id: str, req: FileRequest) -> TransactionFiled:
    """File a payment gate 1 found below every threshold. The gate run must say so: the API checks it."""
    repo = TransactionRepository(uow.session)
    tx = await _transaction(repo, transaction_id, for_update=True)
    facts = await gates.gate_run_facts(uow, req.gate_run_id)
    if facts != ("aml.gate1-entry", transaction_id, "below-threshold") or req.outcome != "below-threshold":
        raise RuleRefused(409, "NOT_BELOW_THRESHOLD", "Cannot file this payment",
                          f"Gate run {req.gate_run_id} does not show payment {transaction_id} below threshold.")
    if tx.state not in ("ENRICHED", "FILED"):
        raise RuleRefused(409, "NOT_FILEABLE", "Cannot file this payment",
                          f"Payment {transaction_id} is {tx.state.lower()}; only an enriched payment is filed.")
    tx.state, tx.filed_gate_run_id, tx.updated_at = "FILED", req.gate_run_id, uow.now
    uow.audit.record("transaction.filed", "transaction", transaction_id, {"gateRunId": str(req.gate_run_id)},
                     domain="AML")
    return TransactionFiled(transaction_id=transaction_id, state="FILED")


# ---------------------------------------------------------------- gate inputs

async def gate1_inputs(uow: UnitOfWork, transaction_id: str) -> Resolution:
    """aml.gate1-entry: the amount, the 7-day window, the counterparty and the beneficiary country."""
    repo = TransactionRepository(uow.session)
    tx = await _enriched(repo, transaction_id)
    total, near = await repo.window(tx.entity_key or tx.transaction_id, tx.received_at, WINDOW_DAYS)
    payment = f"{FIVE_SERIES} {transaction_id}"
    window = f"platform-api {WINDOW_DAYS}-day window"
    return Resolution([
        ResolvedInput("unusualFlag", tx.unusual_flag, payment),
        ResolvedInput("counterpartyId", tx.counterparty_id, payment),
        ResolvedInput("amountUsd", float(tx.amount_usd or 0), payment),
        ResolvedInput("amountUsdSum7d", float(total), window),
        ResolvedInput("beneficiaryCtry", tx.beneficiary_ctry, payment),
        ResolvedInput("nearThresholdCount7d", near, window),
    ])


def gate2_resolver(
    profiles: ClientProfiles, interpreter: ProfileInterpreter
) -> Callable[[UnitOfWork, str], Awaitable[Resolution]]:
    async def resolve(uow: UnitOfWork, transaction_id: str) -> Resolution:
        """aml.gate2-profile: the model's reading of the payment against the client's CARE profile."""
        tx = await _enriched(TransactionRepository(uow.session), transaction_id)
        payment = f"{FIVE_SERIES} {transaction_id}"
        profile = await profiles.profile(tx.client_id or "")
        if profile is None:
            # No profile, nothing to compare: uncertain, which the ruleset maps to mismatch.
            return Resolution([
                ResolvedInput("profileVerdict", "uncertain", f"CARE has no profile for {tx.client_id}"),
                ResolvedInput("amountUsd", float(tx.amount_usd or 0), payment),
            ], llm={"verdict": "uncertain", "reason": "No CARE profile"})
        judgement = await interpreter.judge(_payment(tx), profile)
        model = (judgement.llm or {}).get("modelId", "model")
        return Resolution([
            ResolvedInput("profileVerdict", judgement.verdict, f"{model} reading of CARE profile {profile.client_id}"),
            ResolvedInput("amountUsd", float(tx.amount_usd or 0), payment),
            ResolvedInput("profileMaxAmountUsd", float(profile.max_amount_usd), f"CARE profile {profile.client_id}"),
            ResolvedInput("countryInProfile", tx.beneficiary_ctry in profile.countries,
                          f"CARE profile {profile.client_id}"),
        ], llm={**(judgement.llm or {}), "verdict": judgement.verdict, "reason": judgement.reason})

    return resolve


def gate3_resolver(
    profiles: ClientProfiles, screening: Screening
) -> Callable[[UnitOfWork, str], Awaitable[Resolution]]:
    async def resolve(uow: UnitOfWork, transaction_id: str) -> Resolution:
        """aml.gate3-risk: live screening of the counterparty, and the client's risk rating and PEP flag."""
        tx = await _enriched(TransactionRepository(uow.session), transaction_id)
        try:
            result = await screening.screen(tx.counterparty_name or "", tx.beneficiary_ctry or "")
        except ScreeningUnavailable as exc:
            log.warning("gate3.screening_unavailable", transaction_id=transaction_id)
            raise ServiceUnavailable(f"The screening provider did not answer, so payment {transaction_id} stays "
                                     "held.") from exc
        profile = await profiles.profile(tx.client_id or "")
        care = f"CARE profile {tx.client_id}"
        return Resolution([
            ResolvedInput("screeningHit", result.hit, f"screening {result.reference}"),
            ResolvedInput("screeningScore", result.score, f"screening {result.reference}"),
            ResolvedInput("riskScore", profile.risk_score if profile else None, care),
            ResolvedInput("pepFlag", profile.pep if profile else None, care),
        ], screening_ref=result.reference)

    return resolve


async def after_gate1(uow: UnitOfWork, transaction_id: str, outcome: str, run_id: uuid.UUID) -> None:
    """A payment gate 1 sends into monitoring is held in 5 Series until a card decides it."""
    if outcome != "monitor":
        return
    tx = await _transaction(TransactionRepository(uow.session), transaction_id, for_update=True)
    if tx.state == "ENRICHED":
        tx.state, tx.updated_at = "MONITORING", uow.now
    await request_hold(uow, transaction_id)


# ---------------------------------------------------------------- holds and decisions

async def request_hold(uow: UnitOfWork, transaction_id: str) -> None:
    """Queue the hold (5 Series is called by the jobs worker, with retries). Asked for twice, it runs once."""
    await jobs.enqueue(uow.session, HOLD_JOB, {"transactionId": transaction_id}, now=uow.now,
                       dedupe_key=f"{HOLD_JOB}:{transaction_id}")


async def hold_job(uow: UnitOfWork, payload: dict[str, Any], payments: PaymentSystem) -> None:
    repo = TransactionRepository(uow.session)
    tx = await repo.get(payload["transactionId"], for_update=True)
    if tx is None or tx.hold_state != "none":
        return
    tx.hold_reference = await payments.hold(tx.transaction_id)
    tx.hold_state, tx.updated_at = "held", uow.now
    uow.audit.record("transaction.held", "transaction", tx.transaction_id, {"reference": tx.hold_reference},
                     domain="AML")


async def apply_decision(uow: UnitOfWork, card_type: str, transaction_id: str, payments: PaymentSystem) -> str:
    """An approved UC2 card's write-back. Returns the system of record's reference."""
    repo = TransactionRepository(uow.session)
    tx = await _transaction(repo, transaction_id, for_update=True)
    if card_type == "aml.mlro-escalation":
        reference = await payments.freeze(transaction_id, tx.hold_reference)
        tx.state, tx.hold_state, action = "FROZEN", "frozen", "transaction.frozen"
    elif card_type == "aml.profile-update":
        # The profile is updated in CARE; the payment stays held until it is re-validated from gate 2 (a UC2
        # workflow path not built yet: see n8n-workflows/README.md).
        reference, action = f"CARE-PROFILE-{transaction_id}", "transaction.profile_updated"
    else:  # aml.compliance-decision, aml.gate-exception: the officer cleared the payment
        reference = await payments.release(transaction_id, tx.hold_reference)
        tx.state, tx.hold_state, action = "CLEARED", "released", "transaction.released"
    tx.updated_at = uow.now
    uow.audit.record(action, "transaction", transaction_id, {"cardType": card_type, "reference": reference},
                     domain="AML")
    return reference


async def card_evidence(
    uow: UnitOfWork, transaction_id: str, runs: Sequence[GateRunView], profiles: ClientProfiles
) -> list[EvidenceDraft]:
    """A UC2 card's evidence for the evidence review (cards' SubjectEvidence): the payment, the client's CARE
    profile and, when gate 3 ran, the live screening."""
    tx = await TransactionRepository(uow.session).get(transaction_id)
    if tx is None or tx.enriched_at is None:
        return []
    profile = await profiles.profile(tx.client_id or "")
    items = [
        EvidenceDraft("record", "Payment", f"{FIVE_SERIES} {transaction_id}", _payment_text(tx)),
        EvidenceDraft("record", "Client profile", f"CARE profile {tx.client_id}",
                      _profile_text(profile) if profile else f"CARE has no profile for {tx.client_id}."),
    ]
    gate3 = next((r for r in runs if r.ruleset_key == GATE3), None)
    found = {i.name: i for i in gate3.inputs} if gate3 else {}
    if "screeningHit" in found:
        hit, score = found["screeningHit"], found.get("screeningScore")
        value = score.value if score else None
        shown = int(value) if isinstance(value, float) and value.is_integer() else value
        result = f"possible match, score {shown if shown is not None else 'not given'}" if hit.value else "no match"
        items.append(EvidenceDraft(
            "screening", "Live screening", hit.source[:1].upper() + hit.source[1:],
            f"{tx.counterparty_name} ({tx.beneficiary_ctry}) screened at {hit.read_at:%d %b %Y %H:%M} UTC: {result}."))
    return items


async def describe(uow: UnitOfWork, card_type: str, subject_id: str) -> SubjectInfo | None:
    """How a UC2 card names its payment, and the amount at stake (cards' SubjectDescriber)."""
    if not card_type.startswith("aml."):
        return None
    tx = await TransactionRepository(uow.session).get(subject_id)
    if tx is None or tx.amount is None:
        return None
    return SubjectInfo(subject_id, {"amount": float(tx.amount), "currency": tx.currency or "USD"})


# ---------------------------------------------------------------- for the sweeper

async def stuck(uow: UnitOfWork, older_than_minutes: int) -> list[tuple[str, str]]:
    """(transaction ID, source) of payments registered but never enriched."""
    rows = await TransactionRepository(uow.session).stuck(uow.now - timedelta(minutes=older_than_minutes))
    return [(t.transaction_id, t.source) for t in rows]


async def requeue(uow: UnitOfWork, transaction_id: str, source: str) -> None:
    """Offer a stuck payment to the UC2 poller again."""
    await TransactionRepository(uow.session).requeue_request(transaction_id, source, uow.now)


# ---------------------------------------------------------------- internals

def _new(transaction_id: str, source: str, uow: UnitOfWork, received_at: Any = None) -> Transaction:
    return Transaction(
        transaction_id=transaction_id, source=source, state="RECEIVED", received_at=received_at or uow.now,
        unusual_flag=False, hold_state="none", created_at=uow.now, updated_at=uow.now,
    )


async def _transaction(repo: TransactionRepository, transaction_id: str, *, for_update: bool = False) -> Transaction:
    tx = await repo.get(transaction_id, for_update=for_update)
    if tx is None:
        raise NotFound(f"There is no payment {transaction_id}.")
    return tx


async def _enriched(repo: TransactionRepository, transaction_id: str) -> Transaction:
    tx = await _transaction(repo, transaction_id)
    if tx.enriched_at is None:
        raise RuleRefused(409, "NOT_ENRICHED", "Not enriched yet",
                          f"Payment {transaction_id} has not been read from 5 Series yet; enrich it first.")
    return tx


def _payment(tx: Transaction) -> Payment:
    return Payment(
        transaction_id=tx.transaction_id, client_id=tx.client_id or "", client_name=tx.client_name or "",
        entity_key=tx.entity_key or "", amount=tx.amount or Decimal(0), currency=tx.currency or "USD",
        amount_usd=tx.amount_usd or Decimal(0), counterparty_id=tx.counterparty_id or "",
        counterparty_name=tx.counterparty_name or "", beneficiary_ctry=tx.beneficiary_ctry or "",
        purpose=tx.purpose or "", unusual_flag=tx.unusual_flag, value_date=tx.value_date or tx.received_at.date(),
    )


def _payment_text(tx: Transaction) -> str:
    amount = f"{tx.currency} {tx.amount:,.2f}"
    if tx.currency != "USD":
        amount += f" (USD {tx.amount_usd:,.2f})"
    hold = {"held": f"held in 5 Series ({tx.hold_reference})", "released": "released", "frozen": "frozen"}.get(
        tx.hold_state, "to be held in 5 Series")
    value_date = f"{tx.value_date:%d %b %Y}" if tx.value_date else "not given"
    return (f"{amount} from {tx.client_name} ({tx.client_id}) to {tx.counterparty_name} ({tx.counterparty_id}), "
            f"beneficiary country {tx.beneficiary_ctry}. Purpose: {tx.purpose}. Value date {value_date}. Flagged "
            f"unusual by 5 Series: {'yes' if tx.unusual_flag else 'no'}. The payment is {hold}.")


def _profile_text(profile: ClientProfile) -> str:
    return (f"{profile.name}: expected beneficiary countries {', '.join(profile.countries)}; largest expected "
            f"payment USD {profile.max_amount_usd:,.0f}; expected purposes: {'; '.join(profile.purposes)}. Risk "
            f"rating {profile.risk_score} of 100. PEP: {'yes' if profile.pep else 'no'}.")
