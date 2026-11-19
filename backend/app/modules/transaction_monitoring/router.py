"""HTTP layer for transaction monitoring (UC2). Serves /transactions and /payment-requests, so no shared prefix."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.authz import Perm, permit
from app.core.config import Settings, get_settings
from app.core.principal import Principal
from app.integrations import five_series
from app.modules.transaction_monitoring import service
from app.modules.transaction_monitoring.schemas import (
    ClaimPage,
    ClaimRequest,
    EnrichedTransaction,
    EnrichRequest,
    FileRequest,
    TransactionFiled,
    TransactionIntake,
    TransactionRegistered,
)
from app.shared.idempotency import IdempotentCommand, idempotent

router = APIRouter(tags=["transaction monitoring"])


@router.post(
    "/transactions",
    status_code=201,
    response_model=TransactionRegistered,
    summary="Register a payment for AML monitoring (UC2 intake)",
    responses={200: {"model": TransactionRegistered, "description": "This transaction was registered before"}},
)
async def register(
    body: TransactionIntake,
    _: Principal = Depends(permit(Perm.WORKFLOW_CALL)),
    cmd: IdempotentCommand = Depends(idempotent),
) -> JSONResponse:
    # Idempotent on transactionId (n8n README): a repeat returns the payment with created=false.
    return await cmd.run(lambda uow: service.register(uow, body),
                         status_for=lambda result: 201 if result.created else 200, mode="business-key")


@router.post("/payment-requests/claim", response_model=ClaimPage, summary="Lease new 5 Series payment requests")
async def claim(
    body: ClaimRequest,
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(permit(Perm.WORKFLOW_CALL)),
    cmd: IdempotentCommand = Depends(idempotent),
) -> JSONResponse:
    payments = five_series.payments(settings)
    return await cmd.run(lambda uow: service.claim(uow, principal.actor, body, payments), status_for=lambda _: 200)


@router.post("/transactions/enrich", response_model=EnrichedTransaction, summary="Read the payment from 5 Series")
async def enrich(
    body: EnrichRequest,
    settings: Settings = Depends(get_settings),
    _: Principal = Depends(permit(Perm.WORKFLOW_CALL)),
    cmd: IdempotentCommand = Depends(idempotent),
) -> JSONResponse:
    payments = five_series.payments(settings)
    return await cmd.run(lambda uow: service.enrich(uow, body, payments), status_for=lambda _: 200)


@router.post(
    "/transactions/{transaction_id}/file", response_model=TransactionFiled, summary="File a below-threshold payment"
)
async def file_transaction(
    transaction_id: str,
    body: FileRequest,
    _: Principal = Depends(permit(Perm.WORKFLOW_CALL)),
    cmd: IdempotentCommand = Depends(idempotent),
) -> JSONResponse:
    return await cmd.run(lambda uow: service.file_transaction(uow, transaction_id, body), status_for=lambda _: 200)
