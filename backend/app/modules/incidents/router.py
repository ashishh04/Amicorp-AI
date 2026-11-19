"""HTTP layer for incidents. Validate input, call the service, return schemas."""
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.authz import Perm, permit
from app.core.principal import Principal
from app.db.session import UnitOfWork, get_uow
from app.modules.incidents import service
from app.modules.incidents.schemas import IncidentCreate, IncidentCreated, IncidentView
from app.shared.idempotency import IdempotentCommand, idempotent

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.post(
    "",
    status_code=201,
    response_model=IncidentCreated,
    summary="Record a workflow failure (Platform error handler)",
    responses={200: {"model": IncidentCreated, "description": "This execution's incident already exists"}},
)
async def record_incident(
    body: IncidentCreate,
    _: Principal = Depends(permit(Perm.WORKFLOW_CALL)),
    cmd: IdempotentCommand = Depends(idempotent),
) -> JSONResponse:
    return await cmd.run(
        lambda uow: service.record_incident(uow, body),
        status_for=lambda result: 201 if result.created else 200,
    )


@router.get("/{incident_id}", response_model=IncidentView, summary="Read one incident")
async def get_incident(
    incident_id: uuid.UUID,
    _: Principal = Depends(permit(Perm.INCIDENT_READ)),
    uow: UnitOfWork = Depends(get_uow),
) -> IncidentView:
    return await service.get_incident(uow, incident_id)
