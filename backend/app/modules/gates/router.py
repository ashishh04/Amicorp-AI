"""HTTP layer for gates and rulesets. The wiring below is where each ruleset meets the module that owns its
inputs, and the adapters those inputs need."""
from functools import lru_cache

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.authz import Perm, permit
from app.core.config import get_settings
from app.core.principal import Principal
from app.db.session import UnitOfWork, get_uow
from app.integrations import care, maas, screening
from app.modules.gates import service
from app.modules.gates.ports import GateInputs
from app.modules.gates.schemas import (
    EvaluateRequest,
    EvaluateResult,
    RulesetDraft,
    RulesetPage,
    RulesetTestRequest,
    RulesetTestResult,
    RulesetValidateRequest,
    RulesetValidation,
    RulesetView,
)
from app.modules.statements import service as statements
from app.modules.transaction_monitoring import service as transactions
from app.shared.idempotency import IdempotentCommand, idempotent, idempotent_optional

log = structlog.get_logger()

router = APIRouter(prefix="/gates", tags=["gates"])
rulesets_router = APIRouter(prefix="/rulesets", tags=["rulesets"])


@lru_cache(maxsize=1)
def wiring() -> dict[str, GateInputs]:
    """Each ruleset's inputs. A ruleset whose adapters are not available in this environment answers 501."""
    settings = get_settings()
    wired = {
        "uc1.field-validation": GateInputs("statement", statements.field_validation_inputs),
        "nav.checks": GateInputs("nav-statement", statements.nav_checks_inputs),
        "aml.gate1-entry": GateInputs("transaction", transactions.gate1_inputs, after=transactions.after_gate1),
    }
    try:
        profiles, interpreter = care.profiles(settings), maas.profile_interpreter(settings)
        screener = screening.screening(settings)
    except (NotImplementedError, RuntimeError) as exc:
        log.warning("gates.uc2_not_wired", reason=str(exc))
    else:
        wired["aml.gate2-profile"] = GateInputs("transaction", transactions.gate2_resolver(profiles, interpreter))
        wired["aml.gate3-risk"] = GateInputs("transaction", transactions.gate3_resolver(profiles, screener))
    return wired


@router.post("/evaluate", response_model=EvaluateResult, summary="Evaluate a ruleset for a subject (all workflows)")
async def evaluate(
    body: EvaluateRequest,
    _: Principal = Depends(permit(Perm.WORKFLOW_CALL)),
    cmd: IdempotentCommand = Depends(idempotent),
) -> JSONResponse:
    # n8n keys each evaluation by execution, so a node retry replays the stored run instead of evaluating again.
    return await cmd.run(lambda uow: service.evaluate(uow, body, wiring()), status_for=lambda _: 200)


@rulesets_router.get("", response_model=RulesetPage, summary="Rulesets, their versions and what the caller may do")
async def list_rulesets(
    principal: Principal = Depends(permit(Perm.RULESET_READ)), uow: UnitOfWork = Depends(get_uow)
) -> RulesetPage:
    return await service.list_rulesets(uow, principal)


@rulesets_router.post("/{key}/test", response_model=RulesetTestResult, summary="Run a version on sample inputs")
async def test_ruleset(
    key: str,
    body: RulesetTestRequest,
    _: Principal = Depends(permit(Perm.RULESET_READ)),
    cmd: IdempotentCommand = Depends(idempotent_optional),
) -> RulesetTestResult:
    # No side effects: a repeat is harmless, so the key is accepted and the test simply runs again.
    return await service.test_ruleset(cmd.uow, key, body)


@rulesets_router.post("/{key}/validate", response_model=RulesetValidation, summary="Check a draft before saving")
async def validate(
    key: str,
    body: RulesetValidateRequest,
    _: Principal = Depends(permit(Perm.RULESET_DRAFT)),
    cmd: IdempotentCommand = Depends(idempotent_optional),
) -> RulesetValidation:
    return await service.validate_draft(cmd.uow, key, body.rules)


@rulesets_router.post("/{key}/versions", response_model=RulesetView, summary="Draft a new version (Admin)")
async def create_draft(
    key: str,
    body: RulesetDraft,
    principal: Principal = Depends(permit(Perm.RULESET_DRAFT)),
    cmd: IdempotentCommand = Depends(idempotent_optional),
) -> JSONResponse:
    return await cmd.run(lambda uow: service.save_draft(uow, principal, key, body, None), status_for=lambda _: 200)


@rulesets_router.put("/{key}/versions/{version}", response_model=RulesetView, summary="Edit the draft (Admin)")
async def update_draft(
    key: str,
    version: int,
    body: RulesetDraft,
    principal: Principal = Depends(permit(Perm.RULESET_DRAFT)),
    uow: UnitOfWork = Depends(get_uow),
) -> RulesetView:
    return await service.edit_draft(uow, principal, key, body, version)


@rulesets_router.delete("/{key}/versions/{version}", response_model=RulesetView, summary="Discard the draft (Admin)")
async def discard_draft(
    key: str,
    version: int,
    principal: Principal = Depends(permit(Perm.RULESET_DRAFT)),
    uow: UnitOfWork = Depends(get_uow),
) -> RulesetView:
    return await service.delete_draft(uow, principal, key, version)


@rulesets_router.post(
    "/{key}/versions/{version}/approve", response_model=RulesetView, summary="Approve a draft (four eyes)"
)
async def approve(
    key: str,
    version: int,
    principal: Principal = Depends(permit(Perm.RULESET_APPROVE)),
    cmd: IdempotentCommand = Depends(idempotent_optional),
) -> JSONResponse:
    return await cmd.run(lambda uow: service.approve_version(uow, principal, key, version), status_for=lambda _: 200)
