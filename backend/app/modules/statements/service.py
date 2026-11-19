"""Business rules for statements: intake, extraction results and the UC1 validation workspace.

No HTTP or SQL here. Edits lock the statement row first, so a submit sees every line exactly as it is
committed, and a line edited meanwhile waits for it.
"""
import math
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import structlog

from app.core.errors import NotFound, RuleRefused
from app.core.principal import Principal
from app.db.session import UnitOfWork
from app.modules.cards import service as cards
from app.modules.cards.ports import EvidenceDraft, StatementFacts, SubjectInfo
from app.modules.events import service as events
from app.modules.extraction.ports import ExtractedNav, ExtractedStatement
from app.modules.gates.ports import Resolution, ResolvedInput
from app.modules.identity import service as identity
from app.modules.identity.schemas import PersonRef
from app.modules.lookups import service as lookups
from app.modules.statements import domain
from app.modules.statements.models import NavDetail, Statement, StatementLine
from app.modules.statements.repository import StatementRepository
from app.modules.statements.schemas import (
    CheckFailure,
    ExtractionInfo,
    LineBox,
    LineField,
    LinePatch,
    ReferencesPatch,
    StatementCheck,
    StatementHeader,
    StatementIntake,
    StatementLinePage,
    StatementLineView,
    StatementReference,
    StatementRegistered,
)
from app.shared.action_gate import Gate
from app.shared.schemas import ActionGate

log = structlog.get_logger()

PROFILE_KIND = {"bank-statement": "bank", "nav-statement": "nav"}
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_AMOUNT = Decimal("1e16")  # numeric(18,2)
# LinePatch attribute -> (portal field name, line column)
_PATCH_FIELDS = (
    ("value_date", "valueDate"), ("description", "description"), ("debit", "debit"), ("credit", "credit"),
    ("balance", "balance"), ("en_number", "enNumber"),
)
_REFERENCE_KEYS = (("bank_id", "bankId"), ("account_no", "accountNo"), ("entity", "entity"))


@dataclass(frozen=True)
class ExtractionTarget:
    statement_id: uuid.UUID
    object_key: str
    received_at: datetime


# ---------------------------------------------------------------- portal: read

async def header(uow: UnitOfWork, principal: Principal, statement_id: uuid.UUID) -> StatementHeader:
    async with uow:
        caller = await identity.caller(uow, principal)
        statement, card = await _visible(uow, caller, statement_id)
        return await _header(uow, caller, statement, card)


async def lines(uow: UnitOfWork, principal: Principal, statement_id: uuid.UUID) -> StatementLinePage:
    async with uow:
        caller = await identity.caller(uow, principal)
        statement, _ = await _visible(uow, caller, statement_id)
        rows = await StatementRepository(uow.session).lines(statement.statement_id)
        names = await identity.display_names(uow, {r.corrected_by for r in rows if r.corrected_by})
        edit = _edit_gate(caller, statement)
        return StatementLinePage(items=[_line_view(statement, r, edit, names) for r in rows])


# ---------------------------------------------------------------- portal: edit (Maker)

async def patch_line(
    uow: UnitOfWork, principal: Principal, statement_id: uuid.UUID, line_id: uuid.UUID, patch: LinePatch,
    if_match: str | None,
) -> StatementLineView:
    """PATCH is idempotent by its If-Match, so it runs in its own unit of work without an Idempotency-Key."""
    async with uow:
        return await _patch_line(uow, principal, statement_id, line_id, patch, if_match)


async def _patch_line(
    uow: UnitOfWork, principal: Principal, statement_id: uuid.UUID, line_id: uuid.UUID, patch: LinePatch,
    if_match: str | None,
) -> StatementLineView:
    caller, statement, card = await _editable(uow, principal, statement_id)
    repo = StatementRepository(uow.session)
    line = await _line(repo, statement, line_id)
    etag = _etag(line)
    if not if_match:
        raise RuleRefused(428, "IF_MATCH_REQUIRED", "Reload needed",
                          f"Send line {line.line_no}'s etag in If-Match, so a newer change is never overwritten.")
    if if_match != etag:
        raise RuleRefused(412, "STALE_LINE", "Stale line",
                          f"Line {line.line_no} changed since you loaded it. Reload and try again.")

    changes = await _validated_changes(uow, line, patch)
    if changes:
        for column, value in changes.items():
            setattr(line, column, value)
        fields = [name for attr, name in _PATCH_FIELDS if attr in changes]
        line.confidence = {**line.confidence, **dict.fromkeys(fields, 1.0)}
        line.corrected = [*line.corrected, *(f for f in fields if f not in line.corrected)]
        line.corrected_by = caller.user_id
        # A correction needs a fresh approval.
        line.approved, line.approved_by, line.approved_at = False, None, None
        line.version += 1
        await _touch(uow, statement, card, caller)
        uow.audit.record("statement.line.corrected", "statement", str(statement.statement_id),
                         {"lineNo": line.line_no, "fields": fields})
    names = await identity.display_names(uow, [line.corrected_by] if line.corrected_by else [])
    return _line_view(statement, line, _edit_gate(caller, statement), names)


async def approve_line(
    uow: UnitOfWork, principal: Principal, statement_id: uuid.UUID, line_id: uuid.UUID
) -> StatementLineView:
    caller, statement, card = await _editable(uow, principal, statement_id)
    line = await _line(StatementRepository(uow.session), statement, line_id)
    threshold = _threshold(statement)
    red = domain.flagged(line.confidence, line.corrected, threshold)
    if red:
        raise RuleRefused(422, "REVIEW_REQUIRED", "Review required",
                          f"Line {line.line_no} has a flagged field ({domain.field_list(red)}) below "
                          f"{domain.threshold_text(threshold)} confidence. Correct it before approving.")
    if not line.approved:
        line.approved, line.approved_by, line.approved_at = True, caller.user_id, uow.now
        line.version += 1
        await _touch(uow, statement, card, caller)
        uow.audit.record("statement.line.approved", "statement", str(statement.statement_id),
                         {"lineNo": line.line_no})
    names = await identity.display_names(uow, [line.corrected_by] if line.corrected_by else [])
    return _line_view(statement, line, _edit_gate(caller, statement), names)


async def patch_references(
    uow: UnitOfWork, principal: Principal, statement_id: uuid.UUID, patch: ReferencesPatch
) -> StatementHeader:
    async with uow:
        return await _patch_references(uow, principal, statement_id, patch)


async def _patch_references(
    uow: UnitOfWork, principal: Principal, statement_id: uuid.UUID, patch: ReferencesPatch
) -> StatementHeader:
    caller, statement, card = await _editable(uow, principal, statement_id)
    refs = dict(statement.refs)
    changed = []
    for attr, key in _REFERENCE_KEYS:
        if attr in patch.model_fields_set:
            refs[key] = (getattr(patch, attr) or "").strip()
            changed.append(key)
    if changed:
        statement.refs = refs
        await _touch(uow, statement, card, caller)
        uow.audit.record("statement.references.updated", "statement", str(statement.statement_id),
                         {"fields": changed})
    return await _header(uow, caller, statement, card)


async def submit(uow: UnitOfWork, principal: Principal, statement_id: uuid.UUID) -> StatementHeader:
    caller, statement, card = await _editable(uow, principal, statement_id)
    checks = await _checks(uow, statement, await StatementRepository(uow.session).lines(statement.statement_id))
    failed = [c for c in checks if not c.passed]
    if failed:
        failures = [_failure(f, f"{c.id}: {f.message}") for c in failed for f in c.failures]
        raise RuleRefused(
            422, "CHECKS_FAILED", "Checks failed",
            f"{len(failed)} of {len(checks)} requirements-before-save gates failed. The statement stays with you.",
            extra={"failures": failures},
        )
    statement.state = "SUBMITTED"
    await _touch(uow, statement, card, caller)
    if card is not None:
        await cards.record_note(uow, card.card_id, "Submitted statement", "All requirements-before-save gates passed")
    uow.audit.record("statement.submitted", "statement", str(statement.statement_id),
                     {"cardId": str(card.card_id) if card else None})
    return await _header(uow, caller, statement, card)


# ---------------------------------------------------------------- n8n intake and extraction

async def register_statement(uow: UnitOfWork, kind: str, intake: StatementIntake) -> StatementRegistered:
    """Register a received statement, or return the one this object key already registered."""
    repo = StatementRepository(uow.session)
    existing = await repo.by_object_key(intake.object_key)
    if existing is not None:
        return StatementRegistered(statement_id=existing.statement_id, created=False)
    statement = Statement(
        statement_id=uuid.uuid4(), kind=kind, channel=intake.channel, object_key=intake.object_key,
        received_at=intake.received_at, state="REGISTERED", refs={}, version=1, created_at=uow.now,
        updated_at=uow.now,
    )
    await repo.add(statement)
    uow.audit.record("statement.registered", "statement", str(statement.statement_id),
                     {"kind": kind, "channel": intake.channel, "objectKey": intake.object_key})
    return StatementRegistered(statement_id=statement.statement_id, created=True)


async def begin_extraction(uow: UnitOfWork, document_id: uuid.UUID, profile: str) -> None:
    """An extraction job was accepted for this document: check it may be extracted, and mark it so."""
    statement = await StatementRepository(uow.session).get(document_id, for_update=True)
    if statement is None:
        raise NotFound(f"There is no document {document_id}.")
    if statement.kind != PROFILE_KIND[profile]:
        raise RuleRefused(422, "WRONG_PROFILE", "Wrong extraction profile",
                          f"Document {document_id} is a {statement.kind} statement; profile {profile} does not apply.")
    if statement.state not in ("REGISTERED", "FAILED"):
        raise RuleRefused(409, "EXTRACTION_NOT_ALLOWED", "Extraction not allowed",
                          f"Statement {document_id} is {statement.state.lower().replace('_', ' ')}; it is extracted "
                          "once registered, or again after a failed extraction.")
    statement.state = "EXTRACTING"
    statement.updated_at, statement.version = uow.now, statement.version + 1


async def extraction_target(uow: UnitOfWork, document_id: uuid.UUID) -> ExtractionTarget | None:
    statement = await StatementRepository(uow.session).get(document_id)
    if statement is None:
        return None
    return ExtractionTarget(statement.statement_id, statement.object_key, statement.received_at)


async def write_extraction(
    uow: UnitOfWork, statement_id: uuid.UUID, job_id: uuid.UUID, extracted: ExtractedStatement | ExtractedNav
) -> None:
    repo = StatementRepository(uow.session)
    statement = await repo.get(statement_id, for_update=True)
    if statement is None or statement.state != "EXTRACTING":
        log.info("statement.extraction_ignored", statement_id=str(statement_id),
                 state=statement.state if statement else None)
        return
    if isinstance(extracted, ExtractedNav):
        await _write_nav(uow, repo, statement, job_id, extracted)
        return
    statement.bank, statement.account_no = extracted.bank, extracted.account_no
    statement.account_name, statement.currency = extracted.account_name, extracted.currency
    statement.period_from, statement.period_to = extracted.period_from, extracted.period_to
    statement.opening_balance, statement.closing_balance = extracted.opening_balance, extracted.closing_balance
    statement.pages, statement.threshold, statement.refs = extracted.pages, extracted.threshold, extracted.references
    statement.extraction_job_id, statement.model_id, statement.extracted_at = job_id, extracted.model_id, uow.now
    statement.state = "IN_REVIEW"
    statement.updated_at, statement.version = uow.now, statement.version + 1
    await repo.replace_lines(statement_id, [
        StatementLine(
            line_id=uuid.uuid4(), statement_id=statement_id, line_no=x.line_no, value_date=x.value_date,
            description=x.description, debit=x.debit, credit=x.credit, balance=x.balance, en_number=x.en_number,
            confidence=x.confidence, corrected=[], corrected_by=None, approved=False, approved_by=None,
            approved_at=None, box=x.box, version=1,
        )
        for x in extracted.lines
    ])
    uow.audit.record("statement.extracted", "statement", str(statement_id),
                     {"jobId": str(job_id), "lines": len(extracted.lines), "modelId": extracted.model_id})


async def extraction_failed(uow: UnitOfWork, statement_id: uuid.UUID, error: str) -> None:
    statement = await StatementRepository(uow.session).get(statement_id, for_update=True)
    if statement is None or statement.state != "EXTRACTING":
        return
    statement.state = "FAILED"
    statement.updated_at, statement.version = uow.now, statement.version + 1
    uow.audit.record("statement.extraction_failed", "statement", str(statement_id), {"error": error[:200]})


# ---------------------------------------------------------------- for cards and gates

async def card_facts(uow: UnitOfWork, subject_id: str) -> StatementFacts | None:
    """The statement behind a UC1 card (cards' StatementLookup). Call inside an open unit of work."""
    statement_id = _uuid(subject_id)
    repo = StatementRepository(uow.session)
    statement = await repo.get(statement_id) if statement_id else None
    if statement is None or statement.state not in domain.REVIEW_STATES:
        return None
    approved, total = await repo.progress(statement.statement_id)
    return StatementFacts(
        statement_id=str(statement.statement_id), status=statement.state, approved=approved, total=total,
        source=statement.object_key, pages=statement.pages, model_id=statement.model_id,
        extraction_job_id=str(statement.extraction_job_id) if statement.extraction_job_id else None,
    )


async def describe_subject(uow: UnitOfWork, card_type: str, subject_id: str) -> SubjectInfo | None:
    """How a UC1 card names its statement, and the closing balance at stake (cards' SubjectDescriber)."""
    statement_id = _uuid(subject_id)
    if not card_type.startswith(("uc1.", "nav.")) or statement_id is None:
        return None
    repo = StatementRepository(uow.session)
    statement = await repo.get(statement_id)
    if statement is None:
        return None
    if card_type.startswith("nav."):
        nav = await repo.nav_detail(statement_id)
        if nav is None:
            return SubjectInfo(statement.object_key.rsplit("/", 1)[-1])
        return SubjectInfo(f"{nav.fund_name} {nav.share_class}, {nav.valuation_date:%d %b %Y}",
                           {"amount": float(nav.total_nav), "currency": nav.currency})
    if statement.state in domain.REVIEW_STATES and statement.period_to is not None:
        value = None
        if statement.closing_balance is not None and statement.currency:
            value = {"amount": float(statement.closing_balance), "currency": statement.currency}
        return SubjectInfo(f"{statement.account_name}, {statement.bank}, {statement.period_to:%b %Y}", value)
    return SubjectInfo(statement.object_key.rsplit("/", 1)[-1])


async def card_evidence(uow: UnitOfWork, card_type: str, subject_id: str) -> list[EvidenceDraft]:
    """A UC1 or UC3 card's evidence about its statement, for the evidence review (cards' SubjectEvidence). A UC1
    validation card needs none: the portal lists the extracted statement itself. Call inside a unit of work."""
    statement_id = _uuid(subject_id)
    repo = StatementRepository(uow.session)
    statement = await repo.get(statement_id) if statement_id else None
    if statement is None or card_type == cards.UC1_CARD:
        return []
    received = f"Received {statement.received_at:%d %b %Y %H:%M} UTC by {statement.channel}"
    nav = await repo.nav_detail(statement.statement_id) if statement.kind == "nav" else None
    if nav is None:
        return [EvidenceDraft("document", "Source document", statement.object_key,
                              f"{received}; extraction {statement.state.lower()}.")]
    tolerance = await lookups.fund_tolerance(uow, nav.fund_code, nav.share_class)
    move = (nav.nav_per_share - nav.previous_nav_per_share) / nav.previous_nav_per_share * 100
    age = domain.business_days_between(nav.valuation_date, statement.received_at.date())
    return [EvidenceDraft("document", "NAV statement", statement.object_key, (
        f"{nav.fund_name} class {nav.share_class} ({nav.fund_code}), valued {nav.valuation_date:%d %b %Y}, {age} "
        f"business day(s) before it arrived. NAV per share {nav.currency} {nav.nav_per_share:,.6f}, previous "
        f"{nav.previous_nav_per_share:,.6f} ({move:+.2f} %; fund tolerance "
        f"{f'{tolerance} %' if tolerance is not None else 'missing'}). Shares in issue {nav.shares_in_issue:,.4f}; "
        f"register {nav.register_shares:,.4f}. Total NAV {nav.currency} {nav.total_nav:,.2f}. {received}."))]


async def field_validation_inputs(uow: UnitOfWork, subject_id: str) -> list[ResolvedInput]:
    """The inputs of ruleset uc1.field-validation, read from the extracted statement."""
    statement_id = _uuid(subject_id)
    repo = StatementRepository(uow.session)
    statement = await repo.get(statement_id) if statement_id else None
    if statement is None:
        raise NotFound(f"There is no statement {subject_id}.")
    if statement.state not in domain.REVIEW_STATES or statement.period_from is None or statement.period_to is None:
        raise RuleRefused(409, "NOT_EXTRACTED", "Not extracted yet",
                          f"Statement {subject_id} has no extracted lines yet.")
    rows = await repo.lines(statement.statement_id)
    facts = [_facts(r) for r in rows]
    confidences = [Decimal(str(c)) for r in rows for c in r.confidence.values()]
    source = f"extraction {statement.extraction_job_id}"
    return [
        ResolvedInput("pages", statement.pages or 0, source),
        ResolvedInput("minConfidence", float(min(confidences)) if confidences else 0.0, source),
        ResolvedInput("balanceBreaks", len(domain.balance_failures(statement.opening_balance or Decimal(0), facts)),
                      "platform-api balance check"),
        ResolvedInput("datesOutsidePeriod",
                      len(domain.date_failures(statement.period_from, statement.period_to, facts)),
                      "platform-api period check"),
    ]


async def nav_checks_inputs(uow: UnitOfWork, subject_id: str) -> Resolution:
    """The inputs of ruleset nav.checks, read from the extracted NAV statement and the fund's template."""
    statement_id = _uuid(subject_id)
    repo = StatementRepository(uow.session)
    statement = await repo.get(statement_id) if statement_id else None
    if statement is None or statement.kind != "nav":
        raise NotFound(f"There is no NAV statement {subject_id}.")
    nav = await repo.nav_detail(statement.statement_id)
    if nav is None or statement.state not in domain.REVIEW_STATES:
        raise RuleRefused(409, "NOT_EXTRACTED", "Not extracted yet",
                          f"NAV statement {subject_id} is not extracted yet.")
    tolerance = await lookups.fund_tolerance(uow, nav.fund_code, nav.share_class)
    move = abs((nav.nav_per_share - nav.previous_nav_per_share) / nav.previous_nav_per_share * 100)
    source = f"extraction {statement.extraction_job_id}"
    template = f"fund template {nav.fund_code}/{nav.share_class}"
    return Resolution([
        ResolvedInput("valuationAgeBusinessDays",
                      domain.business_days_between(nav.valuation_date, statement.received_at.date()), source),
        ResolvedInput("navMovePctAbs", float(round(move, 2)), source),
        # No template, no tolerance: every move is an exception (fail closed).
        ResolvedInput("tolerancePct", float(tolerance) if tolerance is not None else 0.0,
                      template if tolerance is not None else f"{template} missing, so zero"),
        ResolvedInput("sharesReconciled", nav.shares_in_issue == nav.register_shares, f"{source} and the register"),
    ])


async def nav_published(uow: UnitOfWork, subject_id: str, reference: str) -> None:
    """An approved NAV was published to Valuefy (the nav.approval write-back)."""
    statement_id = _uuid(subject_id)
    statement = await StatementRepository(uow.session).get(statement_id, for_update=True) if statement_id else None
    if statement is None:
        return
    statement.state, statement.updated_at, statement.version = "SUBMITTED", uow.now, statement.version + 1
    uow.audit.record("nav.published", "statement", subject_id, {"reference": reference})


async def stuck_statements(uow: UnitOfWork, kind: str, older_than_minutes: int) -> list[uuid.UUID]:
    """Statements registered at least this long ago whose extraction was never requested."""
    before = uow.now - timedelta(minutes=older_than_minutes)
    rows = await StatementRepository(uow.session).registered_before(kind, before)
    return [s.statement_id for s in rows]


# ---------------------------------------------------------------- internals

async def _write_nav(
    uow: UnitOfWork, repo: StatementRepository, statement: Statement, job_id: uuid.UUID, nav: ExtractedNav
) -> None:
    statement.currency, statement.pages, statement.model_id = nav.currency, nav.pages, nav.model_id
    statement.period_from = statement.period_to = nav.valuation_date
    statement.closing_balance, statement.refs = nav.total_nav, {}
    statement.extraction_job_id, statement.extracted_at, statement.state = job_id, uow.now, "IN_REVIEW"
    statement.updated_at, statement.version = uow.now, statement.version + 1
    await repo.replace_nav_detail(NavDetail(
        statement_id=statement.statement_id, fund_code=nav.fund_code, fund_name=nav.fund_name,
        share_class=nav.share_class, currency=nav.currency, valuation_date=nav.valuation_date,
        nav_per_share=nav.nav_per_share, previous_nav_per_share=nav.previous_nav_per_share,
        shares_in_issue=nav.shares_in_issue, register_shares=nav.register_shares, total_nav=nav.total_nav,
    ))
    uow.audit.record("statement.extracted", "statement", str(statement.statement_id),
                     {"jobId": str(job_id), "kind": "nav", "modelId": nav.model_id})


async def _visible(
    uow: UnitOfWork, caller: identity.Caller, statement_id: uuid.UUID, *, for_update: bool = False
) -> tuple[Statement, cards.SubjectCard | None]:
    statement = await StatementRepository(uow.session).get(statement_id, for_update=for_update)
    if statement is None or statement.kind != "bank":
        raise NotFound(f"Statement {statement_id} does not exist.")
    card = await cards.subject_card(uow, cards.UC1_CARD, str(statement_id))
    if not cards.can_see(cards.UC1_CARD, card, caller):
        team = card.team if card else cards.team_of(cards.UC1_CARD)
        raise RuleRefused(403, "OUTSIDE_SCOPE", "Outside your scope",
                          f"Statement {statement_id} belongs to the {team} team.")
    if statement.state not in domain.REVIEW_STATES:
        raise RuleRefused(409, "NOT_EXTRACTED", "Not ready for review",
                          f"Statement {statement_id} is {statement.state.lower()}; it opens for review once "
                          "extraction finishes.")
    return statement, card


async def _editable(
    uow: UnitOfWork, principal: Principal, statement_id: uuid.UUID
) -> tuple[identity.Caller, Statement, cards.SubjectCard | None]:
    caller = await identity.caller(uow, principal)
    if caller.auditor_only:
        raise RuleRefused(403, "READ_ONLY", "Read only", "Auditors have read-only access; every change is refused.")
    statement, card = await _visible(uow, caller, statement_id, for_update=True)
    gate = _edit_gate(caller, statement)
    if not gate.allowed:
        raise RuleRefused(gate.status, "EDIT_REFUSED", "Read only", gate.reason or "Not allowed.")
    return caller, statement, card


def _edit_gate(caller: identity.Caller, statement: Statement) -> Gate:
    return domain.edit_gate(statement.state, caller.roles, caller.teams, cards.team_of(cards.UC1_CARD))


async def _line(repo: StatementRepository, statement: Statement, line_id: uuid.UUID) -> StatementLine:
    line = await repo.line_for_update(statement.statement_id, line_id)
    if line is None:
        raise NotFound(f"Line {line_id} does not exist.")
    return line


async def _touch(
    uow: UnitOfWork, statement: Statement, card: cards.SubjectCard | None, caller: identity.Caller
) -> None:
    """Record the change on the statement, and the caller as the card's maker (LLD, maker-checker)."""
    statement.updated_at, statement.version = uow.now, statement.version + 1
    if card is not None:
        await cards.set_maker(uow, card.card_id, caller)
    # Open workspaces re-read the statement; the event carries the card's scope so only its team sees it.
    events.publish(uow, "statement.updated",
                   {"statementId": str(statement.statement_id), "cardId": str(card.card_id) if card else None},
                   card_type=cards.UC1_CARD, team=card.team if card else cards.team_of(cards.UC1_CARD),
                   owner_oid=card.owner_id if card else None)


async def _validated_changes(uow: UnitOfWork, line: StatementLine, patch: LinePatch) -> dict[str, Any]:
    """Every field the Maker sent, checked, as {column: value}. Nothing changes if one is invalid."""
    changes: dict[str, Any] = {}
    sent = patch.model_fields_set
    n = line.line_no
    if "value_date" in sent:
        raw = patch.value_date or ""
        try:
            if not _ISO_DATE.match(raw):
                raise ValueError(raw)
            changes["value_date"] = date.fromisoformat(raw)
        except ValueError as exc:
            raise _invalid(f"Line {n}: the value date must be YYYY-MM-DD.") from exc
    if "description" in sent:
        if not patch.description:
            raise _invalid(f"Line {n}: the description cannot be empty.")
        changes["description"] = patch.description
    for attr in ("debit", "credit", "balance"):
        if attr in sent:
            changes[attr] = _amount(n, attr, getattr(patch, attr))
    if "en_number" in sent:
        code = patch.en_number
        if not code or code not in await lookups.en_number_names(uow, [code]):
            raise RuleRefused(422, "UNKNOWN_EN_NUMBER", "Unknown EN number",
                              f"{code or 'An empty value'} is not in today’s EN lookup table (5 Series).")
        changes["en_number"] = code
    return changes


def _amount(line_no: int, name: str, value: float | None) -> Decimal | None:
    if value is None:
        return None
    if not math.isfinite(value):
        raise _invalid(f"Line {line_no}: {name} must be a number or empty.")
    amount = Decimal(str(value))
    if name in ("debit", "credit") and amount < 0:
        raise _invalid(f"Line {line_no}: {name} cannot be negative.")
    exponent = amount.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise _invalid(f"Line {line_no}: {name} has more than two decimal places.")
    if abs(amount) >= _MAX_AMOUNT:
        raise _invalid(f"Line {line_no}: {name} is too large.")
    return amount


def _invalid(detail: str) -> RuleRefused:
    return RuleRefused(422, "INVALID_VALUE", "Invalid value", detail)


async def _header(
    uow: UnitOfWork, caller: identity.Caller, statement: Statement, card: cards.SubjectCard | None
) -> StatementHeader:
    rows = await StatementRepository(uow.session).lines(statement.statement_id)
    references = await _references(uow, statement)
    checks = await _checks(uow, statement, rows, references)
    edit = _edit_gate(caller, statement)
    return StatementHeader(
        id=str(statement.statement_id), card_id=str(card.card_id) if card else None,
        bank=_text(statement.bank), account_no=_text(statement.account_no),
        account_name=_text(statement.account_name), currency=_text(statement.currency),
        period_from=statement.period_from.isoformat() if statement.period_from else "-",
        period_to=statement.period_to.isoformat() if statement.period_to else "-",
        opening_balance=float(statement.opening_balance or 0), closing_balance=float(statement.closing_balance or 0),
        pages=statement.pages or 0, status="SUBMITTED" if statement.state == "SUBMITTED" else "IN_REVIEW",
        extraction=ExtractionInfo(
            model_id=_text(statement.model_id), job_id=str(statement.extraction_job_id or "-"),
            completed_at=statement.extracted_at or statement.updated_at,
            threshold=float(_threshold(statement)),
        ),
        references=[StatementReference(key=r.key, label=r.label, value=r.value, valid=r.valid, message=r.message)
                    for r in references],
        checks=[StatementCheck(id=c.id, desc=c.desc, status="pass" if c.passed else "fail",
                               failures=[CheckFailure(**_failure(f, f.message)) for f in c.failures])
                for c in checks],
        editable=ActionGate(allowed=edit.allowed, reason=edit.reason),
    )


async def _references(uow: UnitOfWork, statement: Statement) -> list[domain.Reference]:
    entity = statement.refs.get("entity", "")
    names = await lookups.en_number_names(uow, [entity])
    return domain.references(
        statement.refs, bank=statement.bank or "", account_no=statement.account_no or "",
        bic_on_file=await lookups.bank_bic(uow, statement.bank), entity_name=names.get(entity),
    )


async def _checks(
    uow: UnitOfWork, statement: Statement, rows: Sequence[StatementLine],
    references: list[domain.Reference] | None = None,
) -> list[domain.Check]:
    if references is None:
        references = await _references(uow, statement)
    known = await lookups.en_number_names(uow, [r.en_number for r in rows if r.en_number])
    return domain.checks(
        period_from=statement.period_from or date.min, period_to=statement.period_to or date.max,
        opening=statement.opening_balance or Decimal(0), closing=statement.closing_balance or Decimal(0),
        lines=[_facts(r) for r in rows], refs=references, known_en_numbers=known.keys(),
    )


def _facts(line: StatementLine) -> domain.LineFacts:
    return domain.LineFacts(
        line_no=line.line_no, value_date=line.value_date, debit=line.debit, credit=line.credit,
        balance=line.balance, en_number=line.en_number, approved=line.approved,
    )


def _line_view(
    statement: Statement, line: StatementLine, edit: Gate, names: dict[uuid.UUID, str]
) -> StatementLineView:
    red = domain.flagged(line.confidence, line.corrected, _threshold(statement))
    approve = domain.approve_gate(edit, line.approved, red)
    corrected_by = None
    if line.corrected_by is not None:
        corrected_by = PersonRef(id=str(line.corrected_by), name=names.get(line.corrected_by, "Unknown user"))
    return StatementLineView(
        line_id=str(line.line_id), line_no=line.line_no, value_date=line.value_date.isoformat(),
        description=line.description, debit=_float(line.debit), credit=_float(line.credit),
        balance=_float(line.balance), en_number=line.en_number,
        confidence=cast(dict[LineField, float], line.confidence),
        corrected=cast(list[LineField], list(line.corrected)), corrected_by=corrected_by, approved=line.approved,
        approve=ActionGate(allowed=approve.allowed, reason=approve.reason), box=LineBox(**line.box),
        etag=_etag(line),
    )


def _failure(failure: domain.Failure, message: str) -> dict[str, Any]:
    out: dict[str, Any] = {"message": message}
    if failure.line_no is not None:
        out["lineNo"] = failure.line_no
    if failure.field is not None:
        out["field"] = failure.field
    return out


def _etag(line: StatementLine) -> str:
    return f'W/"{line.version}"'


def _threshold(statement: Statement) -> Decimal:
    return statement.threshold if statement.threshold is not None else domain.DEFAULT_THRESHOLD


def _float(amount: Decimal | None) -> float | None:
    return None if amount is None else float(amount)


def _text(value: str | None) -> str:
    return value or "-"


def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None
