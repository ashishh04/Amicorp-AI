"""What cards need from outside: an evidence summary and a recommendation (MaaS in DEV/NPR/PRD), the
details of the finding a card was raised for (owned by the scans module, passed in by the worker), the
evidence about a UC1, UC2 or UC3 card's subject (owned by the statements and transaction monitoring modules,
passed in by the worker), and the statement a UC1 card is about (owned by the statements module, passed in by
the router)."""
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.db.session import UnitOfWork
from app.modules.gates.schemas import GateRunView

FindingLookup = Callable[[UnitOfWork, uuid.UUID], Awaitable[dict[str, Any] | None]]


@dataclass(frozen=True)
class EvidenceDraft:
    """One piece of evidence about a card's subject, as the module that owns the subject describes it."""

    kind: Literal["document", "record", "screening"]
    label: str
    source: str
    detail: str


# (uow, card type, subject ID, the card's gate runs) -> the subject's evidence, in the order the portal lists it.
SubjectEvidence = Callable[[UnitOfWork, str, str, Sequence[GateRunView]], Awaitable[list[EvidenceDraft]]]


@dataclass(frozen=True)
class RecommendationRequest:
    card_type: str
    mode: str  # assemble-and-recommend | propose-correction
    subject_id: str
    evidence: dict[str, Any]
    instruction: str | None = None  # the officer's Return-to-AI rationale


@dataclass(frozen=True)
class Recommendation:
    summary: str
    proposed_action: str
    model_id: str
    decision: str  # APPROVE | REJECT | RETURN_TO_AI | DELEGATE
    confidence: float
    citations: tuple[str, ...] = ()  # the evidence items it relies on, by the IDs the portal shows (E1, E2 ...)
    llm: dict[str, Any] | None = None  # prompt key and sha, tokens, cost and latency, stored with the evidence


class Recommender(Protocol):
    async def recommend(self, request: RecommendationRequest) -> Recommendation: ...


@dataclass(frozen=True)
class SubjectInfo:
    """How a card names its subject, and the value at stake, read once when the card is created."""

    label: str
    value: dict[str, Any] | None = None  # {"amount": float, "currency": str}


SubjectDescriber = Callable[[UnitOfWork, str, str], Awaitable[SubjectInfo | None]]  # (uow, card type, subject)


@dataclass(frozen=True)
class StatementFacts:
    """The UC1 statement behind a card: the Maker's progress and where it came from."""

    statement_id: str
    status: str  # IN_REVIEW | SUBMITTED
    approved: int
    total: int
    source: str
    pages: int | None
    extraction_job_id: str | None
    model_id: str | None


StatementLookup = Callable[[UnitOfWork, str], Awaitable[StatementFacts | None]]


class WriteBack(Protocol):
    """Governed write-back of an approved outcome to its system of record (CARE, 5 Series, Valuefy). It runs
    in the write-back job's unit of work, so the subject's own state changes commit with the card's."""

    async def write_back(self, uow: UnitOfWork, card_type: str, subject_id: str, payload: dict[str, Any]) -> str:
        """Returns the system of record's reference for the change."""
        ...


@dataclass(frozen=True)
class EvidenceItem:
    """One piece of a card's evidence as the assistant sees it, under the ID the portal shows (E1, E2 ...)."""

    id: str
    title: str
    source: str
    detail: str


@dataclass(frozen=True)
class AssistantRequest:
    card_type: str
    subject_id: str
    title: str
    question: str
    scope: str  # card | entities
    evidence: tuple[EvidenceItem, ...]


@dataclass(frozen=True)
class AssistantReply:
    answer: str
    citations: tuple[str, ...]  # evidence IDs; none means the assistant could not ground an answer
    llm: dict[str, Any] | None = None


class Assistant(Protocol):
    """The card assistant (LLD, Embedded assistant): answers from the card's evidence only, or refuses."""

    async def ask(self, request: AssistantRequest) -> AssistantReply: ...


@dataclass(frozen=True)
class ReviewRequest:
    """A UC1, UC2 or UC3 card for the evidence review: what the card is for, what an Approve does, its evidence
    (cited by the IDs the portal shows) and the rule results that raised it (context, not evidence)."""

    card_type: str
    subject_id: str
    title: str
    purpose: str
    on_approval: str
    evidence: tuple[EvidenceItem, ...]
    rule_results: tuple[str, ...]
    instruction: str | None = None  # the officer's Return-to-AI rationale


class EvidenceReviewer(Protocol):
    """Reads a UC1, UC2 or UC3 card's evidence and suggests a decision. It suggests; the officer decides."""

    async def review(self, request: ReviewRequest) -> Recommendation: ...
