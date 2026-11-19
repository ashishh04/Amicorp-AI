"""HTTP layer for the UC1 validation workspace (portal contract, Statements)."""
import uuid

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from app.core.authz import Perm, permit
from app.core.principal import Principal
from app.db.session import UnitOfWork, get_uow
from app.modules.statements import service
from app.modules.statements.schemas import (
    LinePatch,
    ReferencesPatch,
    StatementHeader,
    StatementLinePage,
    StatementLineView,
)
from app.shared.idempotency import IdempotentCommand, idempotent_optional

router = APIRouter(prefix="/statements", tags=["statements"])


@router.get("/{statement_id}", response_model=StatementHeader, summary="Statement header, references and S1-S6")
async def get_header(
    statement_id: uuid.UUID,
    principal: Principal = Depends(permit(Perm.STATEMENT_READ)),
    uow: UnitOfWork = Depends(get_uow),
) -> StatementHeader:
    return await service.header(uow, principal, statement_id)


@router.get("/{statement_id}/lines", response_model=StatementLinePage, summary="Extracted lines with confidence")
async def get_lines(
    statement_id: uuid.UUID,
    principal: Principal = Depends(permit(Perm.STATEMENT_READ)),
    uow: UnitOfWork = Depends(get_uow),
) -> StatementLinePage:
    return await service.lines(uow, principal, statement_id)


@router.patch("/{statement_id}/lines/{line_id}", response_model=StatementLineView, summary="Correct a line (Maker)")
async def patch_line(
    statement_id: uuid.UUID,
    line_id: uuid.UUID,
    body: LinePatch,
    if_match: str | None = Header(default=None, alias="If-Match", max_length=64),
    principal: Principal = Depends(permit(Perm.STATEMENT_EDIT)),
    uow: UnitOfWork = Depends(get_uow),
) -> StatementLineView:
    return await service.patch_line(uow, principal, statement_id, line_id, body, if_match)


@router.post(
    "/{statement_id}/lines/{line_id}/approve", response_model=StatementLineView, summary="Approve a line (Maker)"
)
async def approve_line(
    statement_id: uuid.UUID,
    line_id: uuid.UUID,
    principal: Principal = Depends(permit(Perm.STATEMENT_EDIT)),
    cmd: IdempotentCommand = Depends(idempotent_optional),
) -> JSONResponse:
    return await cmd.run(lambda uow: service.approve_line(uow, principal, statement_id, line_id),
                         status_for=lambda _: 200)


@router.patch("/{statement_id}/references", response_model=StatementHeader, summary="Correct references (Maker)")
async def patch_references(
    statement_id: uuid.UUID,
    body: ReferencesPatch,
    principal: Principal = Depends(permit(Perm.STATEMENT_EDIT)),
    uow: UnitOfWork = Depends(get_uow),
) -> StatementHeader:
    return await service.patch_references(uow, principal, statement_id, body)


@router.post("/{statement_id}/submit", response_model=StatementHeader, summary="Run S1-S6 and submit (Maker)")
async def submit(
    statement_id: uuid.UUID,
    principal: Principal = Depends(permit(Perm.STATEMENT_EDIT)),
    cmd: IdempotentCommand = Depends(idempotent_optional),
) -> JSONResponse:
    return await cmd.run(lambda uow: service.submit(uow, principal, statement_id), status_for=lambda _: 200)
