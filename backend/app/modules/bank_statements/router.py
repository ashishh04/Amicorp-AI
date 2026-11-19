"""POST /v1/bank-statements: the UC1 workflow registers a received bank statement."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.authz import Perm, permit
from app.core.principal import Principal
from app.modules.statements import service as statements
from app.modules.statements.schemas import StatementIntake, StatementRegistered
from app.shared.idempotency import IdempotentCommand, idempotent

router = APIRouter(prefix="/bank-statements", tags=["bank statements"])


@router.post(
    "",
    status_code=201,
    response_model=StatementRegistered,
    summary="Register a received bank statement (UC1 intake)",
    responses={200: {"model": StatementRegistered, "description": "This objectKey was registered before"}},
)
async def register(
    body: StatementIntake,
    _: Principal = Depends(permit(Perm.WORKFLOW_CALL)),
    cmd: IdempotentCommand = Depends(idempotent),
) -> JSONResponse:
    # Idempotent on objectKey (n8n README): a repeat returns the registered statement with created=false.
    return await cmd.run(
        lambda uow: statements.register_statement(uow, "bank", body),
        status_for=lambda result: 201 if result.created else 200,
        mode="business-key",
    )
