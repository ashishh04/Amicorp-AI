"""Business rules for the stuck-item sweeper. No HTTP or SQL here.

n8n's Platform stuck-item sweeper calls POST /v1/maintenance/redrive every 15 minutes. An item is stuck when
the step after it never happened: a statement registered but never sent to extraction, an extraction job
still running or whose outcome n8n never acknowledged, a payment registered but never enriched. Each is
re-driven at most `maxAttempts` times; the next time it is escalated to an incident (once), and n8n tells
platform support.
"""
import uuid
from collections.abc import Mapping
from typing import Literal

import structlog

from app.db.session import UnitOfWork
from app.modules.extraction import service as extraction
from app.modules.extraction.schemas import ExtractionJobRequest
from app.modules.incidents import service as incidents
from app.modules.incidents.schemas import IncidentCreate
from app.modules.maintenance.repository import RedriveRepository
from app.modules.maintenance.schemas import RedriveItem, RedriveRequest, RedriveResult, Scope
from app.modules.statements import service as statements
from app.modules.transaction_monitoring import service as transactions

log = structlog.get_logger()

SWEEPER = "platform.stuck-item-sweeper"
Profile = Literal["bank-statement", "nav-statement"]
STATEMENT_SCOPES: dict[str, tuple[str, Profile]] = {  # scope: (statement kind, extraction profile)
    "uc1.statement": ("bank", "bank-statement"),
    "uc3.nav-statement": ("nav", "nav-statement"),
}


async def redrive(uow: UnitOfWork, req: RedriveRequest, callbacks: Mapping[str, str]) -> RedriveResult:
    sweep_id = uuid.uuid4()
    repo = RedriveRepository(uow.session)
    items: list[RedriveItem] = []

    async def handle(scope: Scope, item_id: str, action: str) -> bool:
        """Count the attempt; False (and an incident) once the item is out of attempts."""
        row = await repo.get(scope, item_id) or repo.start(scope, item_id, uow.now)
        if row.escalated_at is not None:
            return False
        if row.attempts >= req.max_attempts:
            row.escalated_at = uow.now
            await incidents.record_incident(uow, IncidentCreate(
                workflow_id=SWEEPER, workflow_name="Platform stuck-item sweeper", execution_id=f"{scope}:{item_id}",
                failed_node=scope,
                message=f"{scope} {item_id} is still stuck after {row.attempts} re-drives ({action}).",
            ))
            items.append(RedriveItem(scope=scope, item_id=item_id, action="escalated"))
            return False
        row.attempts, row.last_redriven_at = row.attempts + 1, uow.now
        items.append(RedriveItem(scope=scope, item_id=item_id, action="redriven"))
        return True

    for scope in dict.fromkeys(req.scopes):
        if scope in STATEMENT_SCOPES:
            kind, profile = STATEMENT_SCOPES[scope]
            for statement_id in await statements.stuck_statements(uow, kind, req.older_than_minutes):
                if await handle(scope, str(statement_id), "never sent to extraction"):
                    await extraction.submit_job(uow, ExtractionJobRequest(
                        document_id=statement_id, profile=profile, callback_url=callbacks[profile]), callbacks)
        elif scope == "extraction.job":
            for job_id in await extraction.stuck_jobs(uow, req.older_than_minutes):
                if await handle(scope, str(job_id), "extraction or callback not finished"):
                    row = await repo.get(scope, str(job_id))
                    await extraction.redrive_job(uow, job_id, row.attempts if row else 1)
        else:  # uc2.transaction
            for transaction_id, source in await transactions.stuck(uow, req.older_than_minutes):
                if await handle(scope, transaction_id, "never enriched"):
                    await transactions.requeue(uow, transaction_id, source)

    redriven = sum(1 for i in items if i.action == "redriven")
    escalated = len(items) - redriven
    uow.audit.record("maintenance.redrive", "sweep", str(sweep_id), {
        "scopes": list(req.scopes), "redriven": redriven, "escalated": escalated,
    })
    if items:
        log.info("maintenance.redrive", sweep_id=str(sweep_id), redriven=redriven, escalated=escalated)
    return RedriveResult(sweep_id=sweep_id, redriven_count=redriven, escalated_count=escalated, items=items)
