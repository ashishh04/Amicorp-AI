"""Business rules for gates and their rulesets. No HTTP or SQL here.

Rules decide; the record of why is kept. Every evaluation stores what it read, the version that ran and
the rule that matched (rules.gate_run). Fail closed: if the rules cannot decide (a missing input, an
unknown operator, an outcome the ruleset does not list), the ruleset's default outcome applies, which is
always its blocking or review outcome, and the run says why.

Rulesets change under four eyes (portal contract, Rulesets): Admins draft, a Checker of the owning team or
the MLRO approves (the MLRO only for aml.*), never the drafter, and only when every regression case gives its
expected outcome. Approved versions are immutable (a database trigger), so a change is always a new version.
"""
import hashlib
import time
import uuid
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from typing import Any, Literal, cast

import structlog

from app.core.errors import Conflict, NotFound, RuleRefused
from app.core.principal import Principal, Role
from app.db.session import UnitOfWork
from app.modules.gates import jsonlogic
from app.modules.gates.models import GateRun, Ruleset, RulesetVersion
from app.modules.gates.ports import GateInputs, Resolution
from app.modules.gates.repository import GateRepository
from app.modules.gates.schemas import (
    EvaluateRequest,
    EvaluateResult,
    GateInput,
    GateRunView,
    MatchedRule,
    RegressionCase,
    RegressionResult,
    RulesetActions,
    RulesetDraft,
    RulesetPage,
    RulesetTestRequest,
    RulesetTestResult,
    RulesetValidation,
    RulesetVersionView,
    RulesetView,
    RuleTraceView,
    RuleView,
    VersionActions,
)
from app.modules.identity import service as identity
from app.modules.identity.schemas import PersonRef
from app.modules.lookups import service as lookups
from app.shared.action_gate import ALLOW, Gate, deny
from app.shared.audit import canonical_json
from app.shared.schemas import ActionGate

log = structlog.get_logger()

VersionStatus = Literal["draft", "approved", "superseded"]


class NoVersionInForce(Conflict):
    code, title = "NO_VERSION_IN_FORCE", "The ruleset has no approved version in force"


# ---------------------------------------------------------------- evaluation (n8n)

async def evaluate(uow: UnitOfWork, req: EvaluateRequest, wiring: Mapping[str, GateInputs]) -> EvaluateResult:
    started = time.perf_counter()
    repo = GateRepository(uow.session)
    ruleset = await repo.ruleset(req.ruleset)
    if ruleset is None:
        raise NotFound(f"There is no ruleset {req.ruleset}.")
    inputs_for = wiring.get(req.ruleset)
    if inputs_for is None:
        raise RuleRefused(501, "GATE_NOT_WIRED", "Gate not available",
                          f"Ruleset {req.ruleset} cannot read its inputs in this build yet.")
    if req.subject_type != inputs_for.subject_type:
        raise RuleRefused(422, "WRONG_SUBJECT_TYPE", "Wrong subject type",
                          f"Ruleset {req.ruleset} evaluates a {inputs_for.subject_type}, not a {req.subject_type}.")
    version = await repo.version_in_force(req.ruleset, uow.now)
    if version is None:
        raise NoVersionInForce(f"Ruleset {req.ruleset} has no approved version in force.")

    resolved = await inputs_for.resolve(uow, req.subject_id)
    resolution = resolved if isinstance(resolved, Resolution) else Resolution(list(resolved))
    values = {i.name: i.value for i in resolution.inputs}
    try:
        result = jsonlogic.run_rules(version.rules, values, await _reference(uow))
        outcome, rule_id, rule_desc = result.outcome, result.rule_id, result.rule_desc
    except jsonlogic.RuleError as exc:
        outcome, rule_id, rule_desc = ruleset.default_outcome, None, f"The rules could not decide ({exc})"
    if outcome not in ruleset.outcomes:
        outcome, rule_desc = ruleset.default_outcome, f"Rule {rule_id} gave an outcome the ruleset does not list"
        rule_id = None
    if rule_id is None:
        log.warning("gate.failed_closed", ruleset=req.ruleset, version=version.version)

    run = GateRun(
        run_id=uuid.uuid4(), ruleset_key=req.ruleset, version=version.version, subject_type=req.subject_type,
        subject_id=req.subject_id, outcome=outcome, matched_rule=rule_id, matched_desc=rule_desc,
        llm=resolution.llm, screening_ref=resolution.screening_ref, evaluated_at=uow.now,
        duration_ms=round((time.perf_counter() - started) * 1000),
        inputs=[{"name": i.name, "value": _json_value(i.value), "source": i.source, "readAt": uow.now.isoformat()}
                for i in resolution.inputs],
    )
    repo.add_run(run)
    uow.audit.record("gate.evaluated", "gate-run", str(run.run_id), {
        "ruleset": req.ruleset, "version": version.version, "subjectType": req.subject_type,
        "subjectId": req.subject_id, "outcome": outcome, "matchedRule": rule_id,
    }, domain=_domain(req.ruleset))
    if inputs_for.after is not None:
        await inputs_for.after(uow, req.subject_id, outcome, run.run_id)
    return EvaluateResult(run_id=run.run_id, outcome=outcome, ruleset_version=version.version, matched_rule=rule_id)


async def runs_view(uow: UnitOfWork, run_ids: Iterable[uuid.UUID]) -> list[GateRunView]:
    """Gate runs as the card detail shows them. Call inside an open unit of work."""
    views = []
    for run, ruleset_name in await GateRepository(uow.session).runs(run_ids):
        views.append(GateRunView(
            run_id=str(run.run_id), ruleset_key=run.ruleset_key, ruleset_name=ruleset_name,
            ruleset_version=run.version, outcome=run.outcome,
            matched_rule=MatchedRule(id=run.matched_rule or "none", desc=run.matched_desc or ""),
            inputs=[GateInput(name=i["name"], value=i.get("value"), source=i.get("source", ""), read_at=i["readAt"])
                    for i in run.inputs],
            evaluated_at=run.evaluated_at, duration_ms=run.duration_ms,
            model_id=(run.llm or {}).get("modelId"),
        ))
    return views


async def gate_run_facts(uow: UnitOfWork, run_id: uuid.UUID) -> tuple[str, str, str] | None:
    """(ruleset, subject ID, outcome) of a run, for modules that act on a gate's decision. Inside a unit of work."""
    run = await GateRepository(uow.session).run(run_id)
    return (run.ruleset_key, run.subject_id, run.outcome) if run else None


# ---------------------------------------------------------------- ruleset administration (portal)

async def list_rulesets(uow: UnitOfWork, principal: Principal) -> RulesetPage:
    async with uow:
        caller = await identity.caller(uow, principal)
        repo = GateRepository(uow.session)
        rulesets = await repo.rulesets()
        versions = await repo.versions(r.ruleset_key for r in rulesets)
        env = await _reference(uow)
        names = await identity.display_names(uow, _people(versions))
    by_key: dict[str, list[RulesetVersion]] = {}
    for v in versions:
        by_key.setdefault(v.ruleset_key, []).append(v)
    return RulesetPage(items=[_view(rs, by_key.get(rs.ruleset_key, []), caller, names, env) for rs in rulesets])


async def test_ruleset(uow: UnitOfWork, key: str, req: RulesetTestRequest) -> RulesetTestResult:
    """Run one version on the inputs given. No side effects: nothing is stored."""
    async with uow:
        repo = GateRepository(uow.session)
        await _ruleset(repo, key)
        version = await repo.version(key, req.version)
        if version is None:
            raise NotFound(f"Version {req.version} of {key} does not exist.")
        env = await _reference(uow)
    try:
        result = jsonlogic.run_rules(version.rules, req.inputs, env)
    except jsonlogic.RuleError as exc:
        raise RuleRefused(422, "EVALUATION_FAILED", "Evaluation failed", f"{exc}.") from exc
    return RulesetTestResult(
        outcome=result.outcome, matched_rule=MatchedRule(id=result.rule_id, desc=result.rule_desc),
        trace=[RuleTraceView(id=t.id, desc=t.desc, matched=t.matched) for t in result.trace], version=version.version,
    )


async def validate_draft(uow: UnitOfWork, key: str, rules: list[Any]) -> RulesetValidation:
    async with uow:
        ruleset = await _ruleset(GateRepository(uow.session), key)
        env = await _reference(uow)
    return _validation(ruleset, rules, env)


async def save_draft(
    uow: UnitOfWork, principal: Principal, key: str, draft: RulesetDraft, version: int | None
) -> RulesetView:
    """Create the ruleset's one draft (version None) or edit it. The editor becomes the drafter."""
    caller = await identity.caller(uow, principal)
    repo = GateRepository(uow.session)
    ruleset = await _ruleset(repo, key, for_update=True)
    check = _validation(ruleset, draft.rules, await _reference(uow))
    if not check.valid:
        raise RuleRefused(422, "DRAFT_NOT_VALID", "Draft is not valid",
                          f"{len(check.errors)} problem(s) to fix before the draft can be saved.",
                          extra={"failures": [{"message": e} for e in check.errors]})
    note = (draft.note or "").strip()
    if len(note) < 3:
        raise RuleRefused(422, "NOTE_REQUIRED", "Note required",
                          "Say why the rules change, for example the change request.")
    existing = next((v for v in await repo.versions([key]) if v.status == "draft"), None)
    sha = hashlib.sha256(canonical_json(draft.rules).encode()).digest()
    if version is None:
        if existing is not None:
            raise RuleRefused(409, "DRAFT_EXISTS", "Draft exists",
                              f"v{existing.version} is already a draft; edit or discard it first.")
        saved = await repo.max_version(key) + 1
        repo.add_version(RulesetVersion(
            ruleset_key=key, version=saved, status="draft", rules=draft.rules, body_sha256=sha, effective_from=None,
            drafted_by=caller.user_id, drafted_at=uow.now, approved_by=None, approved_at=None, note=note,
        ))
    else:
        if existing is None or existing.version != version:
            raise RuleRefused(409, "NOT_A_DRAFT", "Not a draft", f"Version {version} is not a draft and cannot change.")
        existing.rules, existing.body_sha256, existing.note = draft.rules, sha, note
        existing.drafted_by, existing.drafted_at = caller.user_id, uow.now
        saved = version
    await uow.session.flush()
    uow.audit.record("ruleset.drafted", "ruleset", key, {"version": saved, "note": note, "basedOn": draft.based_on},
                     domain=_domain(key))
    return await _one(uow, caller, ruleset)


async def edit_draft(
    uow: UnitOfWork, principal: Principal, key: str, draft: RulesetDraft, version: int
) -> RulesetView:
    """PUT: idempotent by nature (the same draft twice is the same draft), so it runs in its own unit of work."""
    async with uow:
        return await save_draft(uow, principal, key, draft, version)


async def delete_draft(uow: UnitOfWork, principal: Principal, key: str, version: int) -> RulesetView:
    async with uow:
        return await discard_draft(uow, principal, key, version)


async def discard_draft(uow: UnitOfWork, principal: Principal, key: str, version: int) -> RulesetView:
    caller = await identity.caller(uow, principal)
    repo = GateRepository(uow.session)
    ruleset = await _ruleset(repo, key, for_update=True)
    target = await repo.version(key, version)
    if target is None or target.status != "draft":
        raise RuleRefused(409, "NOT_A_DRAFT", "Not a draft", f"Version {version} is not a draft.")
    await repo.delete_version(key, version)
    uow.audit.record("ruleset.draft.discarded", "ruleset", key, {"version": version}, domain=_domain(key))
    return await _one(uow, caller, ruleset)


async def approve_version(uow: UnitOfWork, principal: Principal, key: str, version: int) -> RulesetView:
    caller = await identity.caller(uow, principal)
    if caller.auditor_only:
        raise RuleRefused(403, "READ_ONLY", "Read only", "Auditors have read-only access; every change is refused.")
    repo = GateRepository(uow.session)
    ruleset = await _ruleset(repo, key, for_update=True)
    target = await repo.version(key, version)
    gate = _approve_gate(ruleset, target, caller, await _reference(uow))
    if not gate.allowed or target is None:
        raise RuleRefused(gate.status, "APPROVAL_REFUSED", "Approval refused", gate.reason or "Not allowed.")
    await repo.supersede_approved(key)
    target.status, target.effective_from = "approved", uow.now
    target.approved_by, target.approved_at = caller.user_id, uow.now
    await uow.session.flush()
    uow.audit.record("ruleset.approved", "ruleset", key, {"version": version, "effectiveFrom": uow.now.isoformat()},
                     domain=_domain(key))
    log.info("ruleset.approved", ruleset=key, version=version)
    return await _one(uow, caller, ruleset)


# ---------------------------------------------------------------- internals

def _approve_gate(
    ruleset: Ruleset, version: RulesetVersion | None, caller: identity.Caller, env: jsonlogic.Env
) -> Gate:
    """Who may approve this version now, and if not, why (the same rule for the hint and the approval)."""
    if version is None or version.status != "draft":
        return deny(409, "Only a draft version can be approved.")
    if caller.has(Role.ADMIN) and not caller.has(Role.CHECKER) and not caller.has(Role.MLRO):
        return deny(403, "Admins draft versions; a Checker or the MLRO approves them.")
    aml = ruleset.ruleset_key.startswith("aml.")
    allowed = caller.has(Role.MLRO) if aml else (
        caller.has(Role.MLRO) or (caller.has(Role.CHECKER) and ruleset.owner_team in caller.teams))
    if not allowed:
        return deny(403, "Only the MLRO approves aml.* rulesets." if aml
                    else f"Only a Checker in {ruleset.owner_team} or the MLRO approves this ruleset.")
    if version.drafted_by == caller.user_id:
        return deny(403, "You drafted this version, so someone else must approve it (four eyes).")
    failing = [r.name for r in _regression(ruleset, version.rules, env) if not r.passed]
    if failing:
        return deny(422, f"{len(failing)} regression case(s) do not give the expected outcome: {', '.join(failing)}.")
    return ALLOW


def _regression(ruleset: Ruleset, rules: Sequence[Any], env: jsonlogic.Env) -> list[RegressionResult]:
    results = []
    for case in ruleset.regression_cases:
        try:
            outcome = jsonlogic.run_rules(rules, case["inputs"], env)
            actual, matched = outcome.outcome, outcome.rule_id
        except jsonlogic.RuleError as exc:
            actual, matched = f"error: {exc}", "-"
        results.append(RegressionResult.model_validate({
            "name": case["name"], "expected": case["expected"], "actual": actual, "matchedRule": matched,
            "pass": actual == case["expected"],
        }))
    return results


def _validation(ruleset: Ruleset, rules: list[Any], env: jsonlogic.Env) -> RulesetValidation:
    errors = jsonlogic.validate(rules, ruleset.outcomes)
    regression = [] if errors else _regression(ruleset, rules, env)
    return RulesetValidation(valid=not errors, errors=errors, regression=regression)


def _view(
    ruleset: Ruleset, versions: Sequence[RulesetVersion], caller: identity.Caller, names: dict[uuid.UUID, str],
    env: jsonlogic.Env,
) -> RulesetView:
    def person(user_id: uuid.UUID) -> PersonRef:
        return PersonRef(id=str(user_id), name=names.get(user_id, "Unknown user"))

    def approve(v: RulesetVersion) -> ActionGate:
        if v.status != "draft":
            return ActionGate(allowed=False)
        gate = _approve_gate(ruleset, v, caller, env)
        return ActionGate(allowed=gate.allowed, reason=gate.reason)

    draft = ActionGate(allowed=True) if caller.has(Role.ADMIN) else ActionGate(
        allowed=False, reason="Admins draft versions under change control.")
    aml = ruleset.ruleset_key.startswith("aml.")
    return RulesetView(
        key=ruleset.ruleset_key, name=ruleset.name, owner=ruleset.owner_team, use_case=ruleset.use_case,
        description=ruleset.description, outcomes=list(ruleset.outcomes),
        versions=[RulesetVersionView(
            version=v.version, status=cast(VersionStatus, v.status), effective_from=v.effective_from,
            drafted_by=person(v.drafted_by), drafted_at=v.drafted_at,
            approved_by=person(v.approved_by) if v.approved_by else None, note=v.note,
            rules=[RuleView(id=str(r.get("id")), desc=str(r.get("desc")), when=r.get("when"), then=str(r.get("then")))
                   for r in v.rules],
            actions=VersionActions(approve=approve(v)),
        ) for v in versions],
        regression_cases=[RegressionCase.model_validate(c) for c in ruleset.regression_cases],
        sample_inputs=dict(ruleset.sample_inputs),
        approvers="the MLRO" if aml else f"a Checker of {ruleset.owner_team} or the MLRO",
        actions=RulesetActions(draft=draft),
    )


async def _one(uow: UnitOfWork, caller: identity.Caller, ruleset: Ruleset) -> RulesetView:
    versions = await GateRepository(uow.session).versions([ruleset.ruleset_key])
    names = await identity.display_names(uow, _people(versions))
    return _view(ruleset, versions, caller, names, await _reference(uow))


async def _ruleset(repo: GateRepository, key: str, *, for_update: bool = False) -> Ruleset:
    ruleset = await repo.ruleset(key, for_update=for_update)
    if ruleset is None:
        raise NotFound(f"Ruleset {key} does not exist.")
    return ruleset


async def _reference(uow: UnitOfWork) -> jsonlogic.Env:
    lists, risk = await lookups.rule_reference(uow)
    return jsonlogic.Env(lists=lists, country_risk=risk)


def _people(versions: Iterable[RulesetVersion]) -> set[uuid.UUID]:
    return {i for v in versions for i in (v.drafted_by, v.approved_by) if i is not None}


def _domain(key: str) -> str:
    return "AML" if key.startswith("aml.") else "General"


def _json_value(value: Any) -> Any:
    return float(value) if isinstance(value, Decimal) else value
