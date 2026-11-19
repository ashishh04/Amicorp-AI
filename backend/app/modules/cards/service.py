"""Business rules for cards. No HTTP or SQL here.

Two callers: n8n creates cards and asks for recommendations; officers read and decide them in the portal.
Every rule the portal shows as a hint comes from domain.decision_gate, the same function the decision
endpoint enforces.
"""
import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

import structlog

from app.ai.errors import LlmError
from app.core.errors import BadRequest, Conflict, NotFound, RuleRefused
from app.core.principal import Principal
from app.db.session import UnitOfWork
from app.modules.cards import domain, ports
from app.modules.cards.models import Card, CardEvent, CardEvidence
from app.modules.cards.ports import (
    Assistant,
    AssistantReply,
    AssistantRequest,
    EvidenceDraft,
    EvidenceItem,
    EvidenceReviewer,
    FindingLookup,
    RecommendationRequest,
    Recommender,
    ReviewRequest,
    StatementFacts,
    StatementLookup,
    SubjectDescriber,
    SubjectEvidence,
    WriteBack,
)
from app.modules.cards.repository import CardQuery, CardRepository
from app.modules.cards.schemas import (
    ActionGate,
    AssistantAnswer,
    AssistantCitation,
    AssistantQuestion,
    CardCounts,
    CardCreate,
    CardCreated,
    CardDetail,
    CardPage,
    CardSummary,
    CardTypePage,
    CardTypeView,
    DecisionRequest,
    Evidence,
    HistoryEntry,
    MandatoryCheck,
    Money,
    PersonPage,
    RecommendAccepted,
    Recommendation,
    RecommendRequest,
    StatementProgress,
)
from app.modules.cards.types import CARD_TYPES, REVIEW_EVIDENCE, USE_CASE_PREFIX
from app.modules.events import service as events
from app.modules.gates import service as gates
from app.modules.gates.schemas import GateRunView
from app.modules.identity import service as identity
from app.modules.identity.models import AppUser
from app.modules.identity.schemas import PersonRef
from app.modules.transaction_monitoring import service as transactions
from app.shared import jobs
from app.shared.action_gate import Gate
from app.shared.business_time import add_business_hours
from app.shared.pagination import clamp_limit, decode_cursor, encode_cursor

log = structlog.get_logger()

RECOMMEND_JOB = "card.recommend"
ASSEMBLE_JOB = "card.assemble"  # the evidence review, step 1: gather the card's evidence
REVIEW_JOB = "card.review"  # step 2: the model reads it
WRITEBACK_JOB = "card.writeback"
UC1_CARD = "uc1.statement-validation"
MLRO_ESCALATION = "aml.mlro-escalation"
# Fields with their own columns; the rest of the request is the card's type-specific payload.
_ENVELOPE = {"type", "subject_id", "severity", "blocks_transaction", "gate_run_id", "gate_run_ids"}
_UNASSIGNED = PersonRef(id="unassigned", name="Unassigned")
_NO_MAKER = PersonRef(id="none", name="None yet")
_STATEMENT_CHECK = ("statement-submitted",
                    "Statement submitted: every line approved and every requirements-before-save gate passed")
_ACTIONS = {
    "NEW": "Created", "ASSEMBLING": "Assembling evidence", "AWAITING_DECISION": "Ready for decision",
    "ESCALATED": "Escalated", "APPROVED": "Approved", "REJECTED": "Rejected", "WRITING_BACK": "Write-back started",
    "WRITEBACK_FAILED": "Write-back failed", "REVERSED": "Reversed", "CLOSED": "Closed",
}


class CardStateConflict(Conflict):
    code, title = "CARD_STATE_CONFLICT", "The card is not in a state that allows this"


@dataclass(frozen=True)
class SubjectCard:
    """What another module may know about the card for one of its subjects."""

    card_id: uuid.UUID
    team: str
    owner_id: uuid.UUID | None
    state: str


# ---------------------------------------------------------------- n8n: create and recommend

async def create_card(
    uow: UnitOfWork, cmd: CardCreate, key: str, describe: SubjectDescriber | None = None
) -> CardCreated:
    """Create a card, or return the one this business key already created (created=False)."""
    repo = CardRepository(uow.session)
    existing = await repo.get_by_key(key)
    if existing is not None:
        return CardCreated(card_id=existing.card_id, created=False, state=existing.state)

    definition = CARD_TYPES[cmd.type]
    info = await describe(uow, cmd.type, cmd.subject_id) if describe else None
    payload = cmd.model_dump(mode="json", by_alias=True, exclude=_ENVELOPE, exclude_none=True)
    if info is not None and info.value is not None:
        payload["value"] = info.value
    single_run = getattr(cmd, "gate_run_id", None)
    card = Card(
        card_id=uuid.uuid4(), type=cmd.type, type_version=definition.version, use_case=definition.use_case,
        title=definition.title.format(subject=info.label if info else cmd.subject_id),
        subject_type=definition.subject_type, subject_id=cmd.subject_id, state="NEW",
        severity=domain.effective_severity(definition.default_severity, getattr(cmd, "severity", None)),
        owner_team=definition.team, owner_oid=None, maker_oid=None,
        due_at=add_business_hours(uow.now, definition.sla_business_hours, definition.calendar),
        blocks_subject=bool(getattr(cmd, "blocks_transaction", False)), payload=payload,
        gate_run_ids=list(getattr(cmd, "gate_run_ids", None) or ([single_run] if single_run else [])),
        delegation_chain=[], return_count=0, idempotency_key=key, created_at=uow.now, updated_at=uow.now,
        version=0,
    )
    await repo.add(card)
    _record_event(uow, repo, card, None, "NEW", {"reason": "created"})
    _move(uow, repo, card, "ASSEMBLING", {"reason": "evidence assembly started"})
    if definition.recommend_mode == REVIEW_EVIDENCE:
        await _queue_recommendation(uow, card, REVIEW_EVIDENCE)  # UC1-UC3 workflows never call /recommend
    elif not definition.recommends:
        _move(uow, repo, card, "AWAITING_DECISION", {"reason": "no AI recommendation for this card type"})
        await _assign_owner(uow, repo, card)

    if card.blocks_subject and card.subject_type == "transaction":
        await transactions.request_hold(uow, card.subject_id)  # the payment waits in 5 Series for the decision
    uow.audit.record("card.created", "card", str(card.card_id), {
        "type": card.type, "subjectId": card.subject_id, "severity": card.severity, "team": card.owner_team,
        "dueAt": card.due_at.isoformat(), "blocksSubject": card.blocks_subject, "state": card.state,
    }, domain=_domain(card))
    _publish(uow, card, "card.created")
    log.info("card.created", card_id=str(card.card_id), card_type=card.type, state=card.state)
    return CardCreated(card_id=card.card_id, created=True, state=card.state)


async def request_recommendation(uow: UnitOfWork, card_id: uuid.UUID, cmd: RecommendRequest) -> RecommendAccepted:
    repo = CardRepository(uow.session)
    card = await repo.get_for_update(card_id)
    if card is None:
        raise NotFound("No card with this ID")
    mode = CARD_TYPES[card.type].recommend_mode
    if mode is None:
        raise CardStateConflict(f"Cards of type {card.type} have no AI recommendation")
    if cmd.mode != mode:
        raise CardStateConflict(f"Cards of type {card.type} take the {mode} recommendation, not {cmd.mode}")
    if card.state != "ASSEMBLING":
        raise CardStateConflict(f"The card is {card.state}; a recommendation is assembled only while ASSEMBLING")
    await _queue_recommendation(uow, card, cmd.mode)
    uow.audit.record("card.recommendation_requested", "card", str(card_id), {"mode": cmd.mode})
    return RecommendAccepted(card_id=card_id, status="QUEUED")


async def recommend_job(
    uow: UnitOfWork, payload: dict[str, Any], recommender: Recommender, find_finding: FindingLookup
) -> None:
    """Jobs worker: gather the evidence, ask for a recommendation, hand the card to a decision-maker.

    The model is asked before the card is locked: its answer can take seconds, and the card's row must not be
    held that long. The state is checked again under the lock."""
    card_id = uuid.UUID(payload["cardId"])
    repo = CardRepository(uow.session)
    card = await repo.get(card_id)
    if card is None or card.state != "ASSEMBLING":
        log.info("card.recommendation_skipped", card_id=str(card_id), state=card.state if card else None)
        return

    evidence: dict[str, Any] = {}
    finding_id = card.payload.get("findingId")
    if finding_id:
        evidence = await find_finding(uow, uuid.UUID(finding_id)) or {}
    request = RecommendationRequest(card.type, payload["mode"], card.subject_id, evidence, payload.get("instruction"))
    result = await recommender.recommend(request)

    card = await repo.get_for_update(card_id)
    if card is None or card.state != "ASSEMBLING":
        log.info("card.recommendation_skipped", card_id=str(card_id), state=card.state if card else None)
        return
    if evidence and not any(e.kind == "finding" for e in await repo.evidence(card_id)):
        repo.add_evidence(CardEvidence(
            evidence_id=uuid.uuid4(), card_id=card_id, kind="finding", ref=finding_id,
            summary=evidence["title"], model_id=None, detail=evidence, created_at=uow.now,
        ))
    await _recommendation_ready(uow, repo, card, result, payload)


async def assemble_job(uow: UnitOfWork, payload: dict[str, Any], subject_evidence: SubjectEvidence) -> None:
    """Jobs worker, the evidence review of a UC1, UC2 or UC3 card, step 1: gather what the subject's own module
    knows and the error the workflow reported, keep it on the card as the portal lists it, then queue step 2.

    The evidence commits here, on its own, so a card whose review fails for good still shows its evidence."""
    card_id = uuid.UUID(payload["cardId"])
    repo = CardRepository(uow.session)
    card = await repo.get(card_id)
    if card is None or card.state != "ASSEMBLING":
        log.info("card.assembly_skipped", card_id=str(card_id), state=card.state if card else None)
        return
    runs = await gates.runs_view(uow, card.gate_run_ids)
    drafts = [*await subject_evidence(uow, card.type, card.subject_id, runs), *_reported_error(card)]
    _keep_evidence(uow, repo, card, drafts, await repo.evidence(card_id))
    await jobs.enqueue(uow.session, REVIEW_JOB, payload, now=uow.now,
                       dedupe_key=f"{REVIEW_JOB}:{card_id}:{card.version}")


async def review_job(
    uow: UnitOfWork, payload: dict[str, Any], reviewer: EvidenceReviewer, statements: StatementLookup
) -> None:
    """Jobs worker, the evidence review, step 2: the model reads the card's evidence next to the rule results that
    raised it, and suggests a decision citing the evidence by the IDs the portal shows. As in recommend_job, the
    model is asked before the card is locked."""
    card_id = uuid.UUID(payload["cardId"])
    repo = CardRepository(uow.session)
    card = await repo.get(card_id)
    if card is None or card.state != "ASSEMBLING":
        log.info("card.review_skipped", card_id=str(card_id), state=card.state if card else None)
        return
    facts = await statements(uow, card.subject_id) if card.type == UC1_CARD else None
    items = tuple(EvidenceItem(e.id, e.label, e.source, e.detail)
                  for e in _evidence(await repo.evidence(card_id), facts))
    rule_results = tuple(f"{_run_title(run)}. {_run_detail(run)}"
                         for run in await gates.runs_view(uow, card.gate_run_ids))
    definition = CARD_TYPES[card.type]
    result = await reviewer.review(ReviewRequest(
        card.type, card.subject_id, card.title, definition.description, definition.on_approval, items, rule_results,
        payload.get("instruction"),
    )) if items else None

    card = await repo.get_for_update(card_id)
    if card is None or card.state != "ASSEMBLING":
        log.info("card.review_skipped", card_id=str(card_id), state=card.state if card else None)
        return
    if result is None:
        await _recommendation_unavailable(uow, repo, card, "Summary unavailable: the card has no evidence to review.",
                                          "no evidence")
        return
    # What the model read is kept with its answer, so the audit shows the exact evidence behind the advice.
    await _recommendation_ready(uow, repo, card, result, payload, seen={
        "evidence": [{"id": i.id, "title": i.title, "source": i.source, "detail": i.detail} for i in items],
        "ruleResults": list(rule_results),
    })


async def recommend_failed(uow: UnitOfWork, payload: dict[str, Any], error: str) -> None:
    """The recommendation, or a step of the evidence review, failed for good: the card still reaches a
    decision-maker, without a summary."""
    repo = CardRepository(uow.session)
    card = await repo.get_for_update(uuid.UUID(payload["cardId"]))
    if card is None or card.state != "ASSEMBLING":
        return
    await _recommendation_unavailable(
        uow, repo, card, "Summary unavailable: the recommendation service did not answer.", error)


async def existing_card_keys(uow: UnitOfWork, keys: set[str]) -> set[str]:
    """Which of these business keys already have a card (used by scans to report only new findings)."""
    return await CardRepository(uow.session).existing_keys(keys)


# ---------------------------------------------------------------- portal: read

async def list_cards(
    uow: UnitOfWork,
    principal: Principal,
    *,
    view: str | None,
    q: str | None,
    use_case: str | None,
    card_type: str | None,
    severity: str | None,
    sort: Literal["dueAt", "-updatedAt"] | None,
    limit: int | None,
    cursor: str | None,
) -> CardPage:
    # No view (global search) means every card in scope, open or closed. The closed view lists the most
    # recently updated first unless the caller asks for dueAt.
    by_recent = sort == "-updatedAt" or (view == "closed" and sort != "dueAt")
    order = "u" if by_recent else "d"
    after = _cursor_position(cursor, order)
    size = clamp_limit(limit)
    async with uow:
        who = _who(await identity.caller(uow, principal))
        rows = await CardRepository(uow.session).page(who, uow.now, CardQuery(
            view=view, text=q, type_prefix=USE_CASE_PREFIX.get(use_case or ""), type=card_type, severity=severity,
            by_recent=by_recent, limit=size, after=after,
        ))
        page = rows[:size]
        names = await identity.display_names(uow, _people(page))
    next_cursor = None
    if len(rows) > size:
        last = page[-1]
        at = last.updated_at if by_recent else last.due_at
        next_cursor = encode_cursor({"o": order, "at": at.isoformat(), "id": str(last.card_id)})
    return CardPage(items=[CardSummary(**_summary_fields(c, names)) for c in page], next_cursor=next_cursor)


async def counts(uow: UnitOfWork, principal: Principal) -> CardCounts:
    async with uow:
        who = _who(await identity.caller(uow, principal))
        numbers = await CardRepository(uow.session).counts(who, uow.now)
    return CardCounts.model_validate(numbers)


async def get_detail(
    uow: UnitOfWork, principal: Principal, card_id: uuid.UUID, statements: StatementLookup
) -> CardDetail:
    async with uow:
        caller = await identity.caller(uow, principal)
        card = await _visible_card(uow, caller, card_id)
        return await _detail(uow, caller, card, statements)


async def delegates(uow: UnitOfWork, principal: Principal, card_id: uuid.UUID) -> PersonPage:
    async with uow:
        caller = await identity.caller(uow, principal)
        card = await _visible_card(uow, caller, card_id)
        people = await _delegates(uow, card)
    return PersonPage(items=[PersonRef(id=str(p.user_id), name=p.display_name) for p in people])


def card_types() -> CardTypePage:
    return CardTypePage(items=[
        CardTypeView(type=d.type, version=d.version, team=d.team, severity=d.severity, sla=d.sla,
                     escalation_role=d.escalation_role, on_approval=d.on_approval, decided_by=d.decided_by)
        for d in CARD_TYPES.values()
    ])


# ---------------------------------------------------------------- portal: decide

async def decide(
    uow: UnitOfWork, principal: Principal, card_id: uuid.UUID, req: DecisionRequest, statements: StatementLookup
) -> CardDetail:
    caller = await identity.caller(uow, principal)
    if caller.auditor_only:
        raise RuleRefused(403, "READ_ONLY", "Read only", "Auditors have read-only access; every change is refused.")
    repo = CardRepository(uow.session)
    card = await _visible_card(uow, caller, card_id, for_update=True)
    facts = await statements(uow, card.subject_id) if card.type == UC1_CARD else None
    people = await _delegates(uow, card)
    names = await identity.display_names(uow, [card.owner_oid] if card.owner_oid else [])
    gate = domain.decision_gate(_card_facts(card, names, _checks(card, facts)), _who(caller), req.decision, len(people))
    if not gate.allowed:
        raise RuleRefused(gate.status, "DECISION_REFUSED", "Decision refused", gate.reason or "Not allowed.")
    rationale = (req.rationale or "").strip()
    if len(rationale) < 3:
        raise RuleRefused(422, "RATIONALE_REQUIRED", "Rationale required",
                          "Tell the assistant what to redo or what is missing." if req.decision == "RETURN_TO_AI"
                          else "Every decision needs a rationale; it is kept in the audit trail.")

    definition = CARD_TYPES[card.type]
    audit: dict[str, Any] = {"decision": req.decision, "rationale": rationale}
    match req.decision:
        case "APPROVE":
            _move(uow, repo, card, "APPROVED", {"action": "Approve", "note": rationale})
            if definition.writes_back:
                _move(uow, repo, card, "WRITING_BACK", {"action": "Write-back started"})
                await jobs.enqueue(uow.session, WRITEBACK_JOB, {"cardId": str(card.card_id)}, now=uow.now,
                                   dedupe_key=f"{WRITEBACK_JOB}:{card.card_id}:{card.version}")
            else:
                _move(uow, repo, card, "CLOSED", {"action": "Closed", "note": "No write-back for this card type"})
        case "REJECT":
            _move(uow, repo, card, "REJECTED", {"action": "Reject", "note": rationale})
            _move(uow, repo, card, "CLOSED", {"action": "Closed"})
        case "RETURN_TO_AI":
            card.return_count += 1
            if card.return_count > domain.RETURN_LIMIT:
                reason = f"More than {domain.RETURN_LIMIT} returns to the AI"
                _move(uow, repo, card, "ESCALATED", {"action": "Escalated", "note": reason, "rationale": rationale})
                uow.audit.record("card.escalated", "card", str(card.card_id), {"reason": reason}, domain=_domain(card))
            else:
                _move(uow, repo, card, "ASSEMBLING", {"action": "Return-to-AI", "note": rationale})
                if definition.recommend_mode:
                    # The card type's own step again, now with the officer's instruction.
                    await _queue_recommendation(uow, card, definition.recommend_mode, rationale)
                else:
                    # No AI summary for this type, so assembly is skipped, as when the card was created. The
                    # return still counts towards the limit.
                    _move(uow, repo, card, "AWAITING_DECISION", {"reason": "no AI recommendation for this card type"})
        case "DELEGATE":
            target = next((p for p in people if str(p.user_id) == req.delegate_to), None)
            if target is None:
                raise RuleRefused(422, "DELEGATE_NOT_ELIGIBLE", "Choose a delegate",
                                  "Pick a Checker in the team who can take this card.")
            card.delegation_chain = [*card.delegation_chain, caller.user_id]
            card.owner_oid = target.user_id
            _note(uow, repo, card, f"Delegated to {target.display_name}", rationale)
            audit["delegateTo"] = str(target.user_id)
            _publish(uow, card, "card.assigned")

    audit["state"] = card.state
    uow.audit.record("card.decided", "card", str(card.card_id), audit, domain=_domain(card))
    _publish(uow, card, "card.updated")
    log.info("card.decided", card_id=str(card.card_id), decision=req.decision, state=card.state)
    return await _detail(uow, caller, card, statements)


async def writeback_job(uow: UnitOfWork, payload: dict[str, Any], writer: WriteBack) -> None:
    """Jobs worker: hand an approved outcome to the system of record, then close the card."""
    repo = CardRepository(uow.session)
    card = await repo.get_for_update(uuid.UUID(payload["cardId"]))
    if card is None or card.state != "WRITING_BACK":
        return
    reference = await writer.write_back(uow, card.type, card.subject_id, card.payload)
    _move(uow, repo, card, "CLOSED", {"action": "Write-back confirmed", "reference": reference})
    uow.audit.record("writeback.confirmed", "card", str(card.card_id), {"reference": reference},
                     domain=_domain(card))
    _publish(uow, card, "card.updated")


async def writeback_failed(uow: UnitOfWork, payload: dict[str, Any], error: str) -> None:
    repo = CardRepository(uow.session)
    card = await repo.get_for_update(uuid.UUID(payload["cardId"]))
    if card is None or card.state != "WRITING_BACK":
        return
    _move(uow, repo, card, "WRITEBACK_FAILED", {"action": "Write-back failed", "note": error[:200]})
    uow.audit.record("writeback.failed", "card", str(card.card_id), {"error": error[:200]}, domain=_domain(card))
    _publish(uow, card, "card.updated")


async def ask(
    uow: UnitOfWork, principal: Principal, card_id: uuid.UUID, req: AssistantQuestion, statements: StatementLookup,
    assistant: Assistant,
) -> AssistantAnswer:
    """The card assistant: answers from the card's evidence only. No citation, no answer."""
    async with uow:
        caller = await identity.caller(uow, principal)
        card = await _visible_card(uow, caller, card_id)
        detail = await _detail(uow, caller, card, statements)
    items = _assistant_evidence(detail)
    reply = AssistantReply(_REFUSAL, ())
    if not _OFF_LIMITS.search(req.question):
        try:
            reply = await assistant.ask(AssistantRequest(
                card.type, card.subject_id, card.title, req.question, req.scope, tuple(items)))
        except LlmError as exc:
            log.warning("assistant.failed", card_id=str(card_id), reason=exc.reason)
    by_id = {i.id: i for i in items}
    cited = [by_id[c] for c in reply.citations if c in by_id]
    answer = AssistantAnswer(
        answer=reply.answer if cited else _REFUSAL, grounded=bool(cited),
        citations=[AssistantCitation(id=e.id, title=e.title, doc_id=e.source, page=n, snippet=e.detail[:300])
                   for n, e in enumerate(cited, start=1)],
    )
    async with uow:  # the question and the answer are logged (LLD, Embedded assistant: logging notice)
        uow.audit.record("assistant.asked", "card", str(card_id), {
            "question": req.question[:500], "scope": req.scope, "grounded": answer.grounded,
            "citations": [c.id for c in answer.citations], "modelId": (reply.llm or {}).get("modelId"),
        }, domain=_domain(card))
    return answer


# ---------------------------------------------------------------- for other modules

def team_of(card_type: str) -> str:
    return CARD_TYPES[card_type].team


async def subject_card(uow: UnitOfWork, card_type: str, subject_id: str) -> SubjectCard | None:
    """The latest card of this type for a subject. Call inside an open unit of work."""
    card = await CardRepository(uow.session).latest_for_subject(card_type, subject_id)
    if card is None:
        return None
    return SubjectCard(card_id=card.card_id, team=card.owner_team, owner_id=card.owner_oid, state=card.state)


def can_see(card_type: str, card: SubjectCard | None, caller: identity.Caller) -> bool:
    """Whether the caller sees a subject: through its card, or by the card type's team before there is one."""
    team = card.team if card else team_of(card_type)
    return domain.can_see(card_type, team, card.owner_id if card else None, _who(caller))


async def set_maker(uow: UnitOfWork, card_id: uuid.UUID, caller: identity.Caller) -> None:
    """Whoever corrects, approves or submits the subject becomes the card's maker (maker-checker)."""
    repo = CardRepository(uow.session)
    card = await repo.get_for_update(card_id)
    if card is None or card.maker_oid == caller.user_id:
        return
    card.maker_oid = caller.user_id
    card.updated_at, card.version = uow.now, card.version + 1


async def record_note(uow: UnitOfWork, card_id: uuid.UUID, action: str, note: str | None = None) -> None:
    """Add a line to the card's history without changing its state (for example, "Submitted statement")."""
    repo = CardRepository(uow.session)
    card = await repo.get_for_update(card_id)
    if card is not None:
        _note(uow, repo, card, action, note)
        _publish(uow, card, "card.updated")


# ---------------------------------------------------------------- internals

_REFUSAL = "I could not find this in the documents you can access."
# Questions about other people or bulk data are refused before any model sees them (the portal mock's rule).
_OFF_LIMITS = re.compile(r"salary|password|other client|all clients|export", re.IGNORECASE)


def _publish(uow: UnitOfWork, card: Card, event_type: str) -> None:
    """A live event for the portal (card.created, card.updated, card.assigned), in this unit of work."""
    data: dict[str, Any] = {"cardId": str(card.card_id), "title": card.title}
    if event_type == "card.assigned":
        data["assignee"] = str(card.owner_oid) if card.owner_oid else None
    else:
        data["state"] = card.state
    events.publish(uow, event_type, data, card_type=card.type, team=card.owner_team, owner_oid=card.owner_oid)


def _assistant_evidence(detail: CardDetail) -> list[EvidenceItem]:
    """The card's evidence as the assistant sees it: the evidence items, then each gate run and the
    recommendation, numbered on from the evidence (E1, E2 ...)."""
    items = [EvidenceItem(e.id, e.label, e.source, e.detail) for e in detail.evidence]
    for run in detail.gate_runs:
        items.append(EvidenceItem(f"E{len(items) + 1}", _run_title(run), f"gate run {run.run_id}", _run_detail(run)))
    if detail.recommendation is not None:
        items.append(EvidenceItem(
            f"E{len(items) + 1}", f"AI recommendation v{detail.recommendation.version}",
            f"model {detail.recommendation.model_id}", detail.recommendation.summary))
    return items


def _run_title(run: GateRunView) -> str:
    return f"{run.ruleset_name} v{run.ruleset_version}: {run.outcome}"


def _run_detail(run: GateRunView) -> str:
    inputs = ", ".join(f"{i.name} = {i.value}" for i in run.inputs)
    return f"Rule {run.matched_rule.id} ({run.matched_rule.desc}). Inputs: {inputs}"


async def _queue_recommendation(uow: UnitOfWork, card: Card, mode: str, instruction: str | None = None) -> None:
    """One job per card version, so a card returned to the AI later gets a fresh one. The evidence review starts
    by assembling the evidence; the other modes go straight to the recommendation."""
    kind = ASSEMBLE_JOB if mode == REVIEW_EVIDENCE else RECOMMEND_JOB
    payload: dict[str, Any] = {"cardId": str(card.card_id), "mode": mode}
    if instruction:
        payload["instruction"] = instruction
    await jobs.enqueue(uow.session, kind, payload, now=uow.now, dedupe_key=f"{kind}:{card.card_id}:{card.version}")


def _reported_error(card: Card) -> list[EvidenceDraft]:
    """The error the workflow reported when it raised an exception card (an extraction, or a UC2 gate)."""
    error = card.payload.get("error")
    if not error:
        return []
    where = card.payload.get("failedAt") or f"extraction job {card.payload.get('extractionJobId')}"
    status = card.payload.get("status")
    return [EvidenceDraft("record", "Reported error", f"Workflow report, {where}",
                          f"{status}: {error}" if status else str(error))]


def _keep_evidence(
    uow: UnitOfWork, repo: CardRepository, card: Card, drafts: Sequence[EvidenceDraft], rows: Sequence[CardEvidence]
) -> None:
    """Keep the assembled evidence on the card. An item assembled before (same kind and label) is brought up to
    date, so a Return-to-AI re-reads the subject while the IDs the portal shows (E1, E2 ...) stay the same."""
    kept = {(r.kind, r.summary): r for r in rows if r.detail.get("assembled")}
    for n, draft in enumerate(drafts):
        detail = {"assembled": True, "text": draft.detail}
        row = kept.get((draft.kind, draft.label))
        if row is not None:
            row.ref, row.detail = draft.source, detail
            continue
        repo.add_evidence(CardEvidence(
            evidence_id=uuid.uuid4(), card_id=card.card_id, kind=draft.kind, ref=draft.source, summary=draft.label,
            model_id=None, detail=detail,
            created_at=uow.now + timedelta(microseconds=n),  # a microsecond apart: they list in assembly order
        ))


async def _recommendation_ready(
    uow: UnitOfWork, repo: CardRepository, card: Card, result: ports.Recommendation, payload: dict[str, Any],
    seen: dict[str, Any] | None = None,
) -> None:
    """Keep the recommendation with its trace, then hand the card to a decision-maker."""
    repo.add_evidence(CardEvidence(
        evidence_id=uuid.uuid4(), card_id=card.card_id, kind="recommendation", ref=None, summary=result.summary,
        model_id=result.model_id, created_at=uow.now,
        detail={"proposedAction": result.proposed_action, "mode": payload["mode"], "decision": result.decision,
                "confidence": result.confidence, "instruction": payload.get("instruction"),
                "citations": list(result.citations), "llm": result.llm, **(seen or {})},
    ))
    _move(uow, repo, card, "AWAITING_DECISION",
          {"action": "Evidence assembled, ready for decision", "modelId": result.model_id})
    await _assign_owner(uow, repo, card)
    audit: dict[str, Any] = {"modelId": result.model_id}
    if result.llm:
        audit |= {"promptKey": result.llm.get("promptKey"), "promptSha": result.llm.get("promptSha")}
    uow.audit.record("card.recommendation_ready", "card", str(card.card_id), audit, domain=_domain(card))
    _publish(uow, card, "card.updated")


async def _recommendation_unavailable(
    uow: UnitOfWork, repo: CardRepository, card: Card, summary: str, error: str
) -> None:
    repo.add_evidence(CardEvidence(
        evidence_id=uuid.uuid4(), card_id=card.card_id, kind="recommendation", ref=None, summary=summary,
        model_id=None, detail={"unavailable": True}, created_at=uow.now,
    ))
    _move(uow, repo, card, "AWAITING_DECISION", {"reason": "recommendation unavailable"})
    await _assign_owner(uow, repo, card)
    uow.audit.record("card.recommendation_unavailable", "card", str(card.card_id), {"error": error[:200]},
                     domain=_domain(card))
    _publish(uow, card, "card.updated")


async def _visible_card(
    uow: UnitOfWork, caller: identity.Caller, card_id: uuid.UUID, *, for_update: bool = False
) -> Card:
    repo = CardRepository(uow.session)
    card = await (repo.get_for_update(card_id) if for_update else repo.get(card_id))
    if card is None:
        raise NotFound(f"Card {card_id} does not exist.")
    if not domain.can_see(card.type, card.owner_team, card.owner_oid, _who(caller)):
        raise RuleRefused(403, "OUTSIDE_SCOPE", "Outside your scope",
                          f"Card {card_id} belongs to the {card.owner_team} team, which is outside your data scope.")
    return card


async def _detail(
    uow: UnitOfWork, caller: identity.Caller, card: Card, statements: StatementLookup
) -> CardDetail:
    definition = CARD_TYPES[card.type]
    repo = CardRepository(uow.session)
    events = await repo.events(card.card_id)
    evidence_rows = await repo.evidence(card.card_id)
    facts = await statements(uow, card.subject_id) if card.type == UC1_CARD else None
    checks = _checks(card, facts)
    people = await _delegates(uow, card)
    names = await identity.display_names(uow, {*_people([card]), *card.delegation_chain, *_actor_ids(events)})
    card_facts = _card_facts(card, names, checks)
    who = _who(caller)
    actions = {d: _hint(domain.decision_gate(card_facts, who, d, len(people))) for d in domain.DECISIONS}
    return CardDetail(
        **_summary_fields(card, names),
        description=definition.description, sla=definition.sla, calendar=definition.calendar,
        escalation_role=definition.escalation_role, on_approval=definition.on_approval, hold=_hold(card),
        recommendation=_recommendation(evidence_rows), evidence=_evidence(evidence_rows, facts),
        gate_runs=await gates.runs_view(uow, card.gate_run_ids), mandatory_checks=checks,
        history=_history(events, names),
        delegation_chain=[_person(i, names, _UNASSIGNED) for i in card.delegation_chain],
        actions=actions,
        statement=StatementProgress(id=facts.statement_id, approved=facts.approved, total=facts.total,
                                    status="SUBMITTED" if facts.status == "SUBMITTED" else "IN_REVIEW")
        if facts else None,
    )


async def _delegates(uow: UnitOfWork, card: Card) -> list[AppUser]:
    """Who may take the card: same deciding role, owning team, neither the owner nor the maker."""
    people = await identity.deciders(uow, card.owner_team, card.type == MLRO_ESCALATION)
    return [p for p in people if p.user_id not in (card.owner_oid, card.maker_oid)]


async def _assign_owner(uow: UnitOfWork, repo: CardRepository, card: Card) -> None:
    """A card awaiting a decision goes to the least-loaded person who may decide it (not its maker)."""
    if card.owner_oid is not None:
        return
    people = [p for p in await identity.deciders(uow, card.owner_team, card.type == MLRO_ESCALATION)
              if p.user_id != card.maker_oid]
    if not people:
        log.warning("card.no_decider", card_id=str(card.card_id), team=card.owner_team)
        return
    load = await repo.open_load(p.user_id for p in people)
    chosen = min(people, key=lambda p: (load.get(p.user_id, 0), p.display_name))
    card.owner_oid = chosen.user_id
    _note(uow, repo, card, f"Assigned to {chosen.display_name}")
    _publish(uow, card, "card.assigned")
    uow.audit.record("card.assigned", "card", str(card.card_id), {"owner": str(chosen.user_id)},
                     domain=_domain(card))


def _move(uow: UnitOfWork, repo: CardRepository, card: Card, to_state: str, detail: dict[str, Any]) -> None:
    domain.check_transition(card.state, to_state)
    _record_event(uow, repo, card, card.state, to_state, detail)
    card.state, card.updated_at, card.version = to_state, uow.now, card.version + 1


def _note(uow: UnitOfWork, repo: CardRepository, card: Card, action: str, note: str | None = None) -> None:
    detail: dict[str, Any] = {"action": action} | ({"note": note} if note else {})
    _record_event(uow, repo, card, card.state, card.state, detail)
    card.updated_at, card.version = uow.now, card.version + 1


def _record_event(
    uow: UnitOfWork, repo: CardRepository, card: Card, from_state: str | None, to_state: str, detail: dict[str, Any]
) -> None:
    repo.add_event(CardEvent(
        card_id=card.card_id, from_state=from_state, to_state=to_state, actor=uow.actor, detail=detail, at=uow.now,
    ))


def _who(caller: identity.Caller) -> domain.Who:
    return domain.Who(user_id=caller.user_id, roles=caller.roles, teams=caller.teams)


def _domain(card: Card) -> str:
    return "AML" if card.type.startswith("aml.") else "General"


def _cursor_position(cursor: str | None, order: str) -> tuple[datetime, uuid.UUID] | None:
    values = decode_cursor(cursor, {"o", "at", "id"})
    if values is None:
        return None
    try:
        if values["o"] != order:
            raise ValueError("sort changed")
        return datetime.fromisoformat(values["at"]), uuid.UUID(values["id"])
    except (TypeError, ValueError) as exc:
        raise BadRequest("The cursor is not valid; start again from the first page") from exc


def _people(cards: Iterable[Card]) -> set[uuid.UUID]:
    return {i for c in cards for i in (c.owner_oid, c.maker_oid) if i is not None}


def _actor_ids(events: Iterable[CardEvent]) -> set[uuid.UUID]:
    ids = set()
    for event in events:
        if event.actor.startswith("user:"):
            try:
                ids.add(uuid.UUID(event.actor[5:]))
            except ValueError:
                continue
    return ids


def _person(user_id: uuid.UUID | None, names: dict[uuid.UUID, str], missing: PersonRef) -> PersonRef:
    if user_id is None:
        return missing
    return PersonRef(id=str(user_id), name=names.get(user_id, "Unknown user"))


def _summary_fields(card: Card, names: dict[uuid.UUID, str]) -> dict[str, Any]:
    value = card.payload.get("value")
    return {
        "id": str(card.card_id), "type": card.type, "title": card.title or card.subject_id,
        "subject_id": card.subject_id, "state": card.state, "severity": card.severity, "team": card.owner_team,
        "owner": _person(card.owner_oid, names, _UNASSIGNED), "maker": _person(card.maker_oid, names, _NO_MAKER),
        "value": Money(amount=value["amount"], currency=value["currency"]) if isinstance(value, dict) else None,
        "created_at": card.created_at, "due_at": card.due_at, "updated_at": card.updated_at,
        "returns": card.return_count,
    }


def _checks(card: Card, facts: StatementFacts | None) -> list[MandatoryCheck]:
    """What the API checks before it accepts an Approve. UC1: the Maker has submitted the statement."""
    if card.type != UC1_CARD:
        return []
    check_id, desc = _STATEMENT_CHECK
    return [MandatoryCheck(id=check_id, desc=desc, met=facts is not None and facts.status == "SUBMITTED")]


def _card_facts(card: Card, names: dict[uuid.UUID, str], checks: Sequence[MandatoryCheck]) -> domain.CardFacts:
    return domain.CardFacts(
        type=card.type, state=card.state, team=card.owner_team, owner_id=card.owner_oid,
        owner_name=names.get(card.owner_oid, "Unknown user") if card.owner_oid else _UNASSIGNED.name,
        maker_id=card.maker_oid, delegations=len(card.delegation_chain),
        unmet_checks=tuple(c.desc for c in checks if not c.met),
    )


def _hint(gate: Gate) -> ActionGate:
    return ActionGate(allowed=gate.allowed, reason=gate.reason)


def _hold(card: Card) -> str | None:
    if not card.blocks_subject:
        return None
    if card.subject_type == "transaction":
        return f"Payment {card.subject_id} is held in 5 Series until this card is decided."
    return f"{card.subject_id} is held until this card is decided."


def _recommendation(rows: Sequence[CardEvidence]) -> Recommendation | None:
    recommendations = [r for r in rows if r.kind == "recommendation"]
    if not recommendations or recommendations[-1].detail.get("unavailable"):
        return None
    latest = recommendations[-1]
    return Recommendation(
        decision=latest.detail.get("decision", "APPROVE"), confidence=float(latest.detail.get("confidence", 0.0)),
        summary=latest.summary, model_id=latest.model_id or "unknown", version=len(recommendations),
        generated_at=latest.created_at, citations=list(latest.detail.get("citations", [])),
    )


def _evidence(rows: Sequence[CardEvidence], facts: StatementFacts | None) -> list[Evidence]:
    items: list[dict[str, Any]] = []
    if facts is not None:
        pages = f"{facts.pages} page{'s' if facts.pages != 1 else ''}" if facts.pages else "Pages unknown"
        progress = "submitted" if facts.status == "SUBMITTED" else "in review"
        items.append({
            "kind": "statement", "label": f"Extracted statement ({facts.total} lines)", "source": facts.source,
            "detail": f"{pages}, extraction job {facts.extraction_job_id}, {facts.model_id or 'model not recorded'}; "
                      f"{facts.approved} of {facts.total} lines approved, {progress}",
            "statement_id": facts.statement_id,
        })
    for row in rows:
        if row.kind == "finding":
            items.append({
                "kind": "lake-row", "label": row.summary,
                "source": f"Lake scan {row.detail.get('scanId')}, rule {row.detail.get('ruleId')}",
                "detail": _describe(row.detail.get("detail")),
            })
        elif row.kind in ("document", "record", "screening"):  # assembled by the evidence review
            items.append({"kind": row.kind, "label": row.summary, "source": row.ref or "",
                          "detail": str(row.detail.get("text", ""))})
    return [Evidence(id=f"E{n}", **item) for n, item in enumerate(items, start=1)]


def _describe(detail: Any) -> str:
    if isinstance(detail, dict):
        return "; ".join(f"{k}: {v}" for k, v in detail.items())[:300]
    return str(detail or "")[:300]


def _history(events: Sequence[CardEvent], names: dict[uuid.UUID, str]) -> list[HistoryEntry]:
    entries = []
    for event in events:
        moved = event.from_state != event.to_state  # a note or an assignment keeps the state
        entries.append(HistoryEntry.model_validate({
            "at": event.at, "actor": identity.actor_name(event.actor, names),
            "action": event.detail.get("action") or _ACTIONS.get(event.to_state, event.to_state),
            "from": event.from_state if moved else None, "to": event.to_state if moved else None,
            "note": event.detail.get("note") or event.detail.get("reason"),
        }))
    return entries
