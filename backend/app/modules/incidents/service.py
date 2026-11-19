"""Business rules for incidents. No HTTP or SQL here."""
import uuid

import structlog

from app.core.errors import NotFound
from app.db.session import UnitOfWork
from app.modules.incidents.models import Incident
from app.modules.incidents.repository import IncidentRepository
from app.modules.incidents.schemas import IncidentCreate, IncidentCreated, IncidentView

log = structlog.get_logger()


def incident_key(cmd: IncidentCreate) -> str | None:
    """One incident per failed execution. Trigger errors have no execution ID, so no business key."""
    if not cmd.execution_id:
        return None
    return f"{cmd.source}:{cmd.workflow_id}:{cmd.execution_id}"


async def record_incident(uow: UnitOfWork, cmd: IncidentCreate) -> IncidentCreated:
    repo = IncidentRepository(uow.session)
    key = incident_key(cmd)
    if key is not None and (existing := await repo.get_by_key(key)) is not None:
        return IncidentCreated(incident_id=existing.incident_id, created=False)

    incident = Incident(
        incident_id=uuid.uuid4(), incident_key=key, source=cmd.source, workflow_id=cmd.workflow_id,
        workflow_name=cmd.workflow_name, execution_id=cmd.execution_id, execution_url=cmd.execution_url,
        failed_node=cmd.failed_node, message=cmd.message, status="OPEN", opened_at=uow.now, updated_at=uow.now,
    )
    repo.add(incident)
    # The message can hold payload fragments, so it stays in the incident row, not in the audit or the logs.
    uow.audit.record("incident.opened", "incident", str(incident.incident_id), {
        "source": cmd.source, "workflowId": cmd.workflow_id, "executionId": cmd.execution_id,
        "failedNode": cmd.failed_node,
    })
    log.info("incident.opened", incident_id=str(incident.incident_id), workflow_id=cmd.workflow_id)
    return IncidentCreated(incident_id=incident.incident_id, created=True)


async def get_incident(uow: UnitOfWork, incident_id: uuid.UUID) -> IncidentView:
    async with uow:
        incident = await IncidentRepository(uow.session).get(incident_id)
        if incident is None:
            raise NotFound("No incident with this ID")
        return IncidentView.model_validate(incident, from_attributes=True)
