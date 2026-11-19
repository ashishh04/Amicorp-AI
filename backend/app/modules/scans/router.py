"""HTTP layer for scans. Validate input, call the service, return schemas."""
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.authz import Perm, permit
from app.core.principal import Principal
from app.db.session import UnitOfWork, get_uow
from app.modules.scans import service
from app.modules.scans.schemas import FindingsPage, ScanAccepted, ScanCreate, ScanView
from app.shared.idempotency import IdempotentCommand, idempotent

router = APIRouter(prefix="/scans", tags=["scans"])


@router.post("", status_code=202, response_model=ScanAccepted, summary="Start a scan (UC4, UC5)")
async def submit_scan(
    body: ScanCreate,
    _: Principal = Depends(permit(Perm.WORKFLOW_CALL)),
    cmd: IdempotentCommand = Depends(idempotent),
) -> JSONResponse:
    return await cmd.run(lambda uow: service.submit_scan(uow, body), status_for=lambda _: 202)


@router.get("/{scan_id}", response_model=ScanView, summary="Scan status: queued, running, completed or failed")
async def get_scan(
    scan_id: uuid.UUID,
    _: Principal = Depends(permit(Perm.SCAN_READ)),
    uow: UnitOfWork = Depends(get_uow),
) -> ScanView:
    return await service.get_scan(uow, scan_id)


@router.get(
    "/{scan_id}/findings",
    response_model=FindingsPage,
    summary="New findings of a completed scan, at most maxNewFindings",
)
async def get_findings(
    scan_id: uuid.UUID,
    _: Principal = Depends(permit(Perm.SCAN_READ)),
    uow: UnitOfWork = Depends(get_uow),
) -> FindingsPage:
    return await service.get_findings(uow, scan_id)
