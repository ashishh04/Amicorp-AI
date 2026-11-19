"""POST /v1/nav-statements: the UC3 workflow registers a received NAV statement."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.authz import Perm, permit
from app.core.principal import Principal
from app.modules.statements import service as statements
from app.modules.statements.schemas import StatementIntake, StatementRegistered
from app.shared.idempotency import IdempotentCommand, idempotent

router = APIRouter(prefix="/nav-statements", tags=["nav statements"])


@router.post(
    "",
    status_code=201,
    response_model=StatementRegistered,
    summary="Register a received NAV statement (UC3 intake)",
    responses={200: {"model": StatementRegistered, "description": "This objectKey was registered before"}},
)
async def register(
    body: StatementIntake,
    _: Principal = Depends(permit(Perm.WORKFLOW_CALL)),
    cmd: IdempotentCommand = Depends(idempotent),
) -> JSONResponse:
    # Idempotent on objectKey, like bank statements: a repeat returns the statement with created=false.
    return await cmd.run(
        lambda uow: statements.register_statement(uow, "nav", body),
        status_for=lambda result: 201 if result.created else 200,
        mode="business-key",
    )
