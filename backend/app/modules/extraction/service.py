"""Business rules for extraction jobs. No HTTP or SQL here.

The contract (n8n README): n8n submits a job, and is later called back on its extraction webhook with
{documentId, jobId, status, error?}. The extraction runs as a background job, and the callback is a job of
its own: a slow or briefly unavailable n8n delays the callback, it never loses it.

Finding F2: a callback URL is never taken on trust. It must be exactly the n8n webhook for the job's
profile under N8N_WEBHOOK_BASE, so the API cannot be made to POST anywhere else.
"""
import uuid
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import structlog

from app.core.errors import RuleRefused
from app.db.session import UnitOfWork
from app.modules.extraction.models import ExtractionJob
from app.modules.extraction.ports import CallbackSender, ExtractedStatement, ExtractionRequest, Extractor
from app.modules.extraction.repository import ExtractionRepository
from app.modules.extraction.schemas import ExtractionJobAccepted, ExtractionJobRequest
from app.modules.statements import service as statements
from app.shared import jobs

log = structlog.get_logger()

EXTRACT_JOB = "extraction.run"
CALLBACK_JOB = "extraction.callback"
CALLBACK_ATTEMPTS = 8  # about eight minutes of backoff before the callback is given up
CALLBACK_PATHS = {
    "bank-statement": "/webhook/bank-statement-extraction-complete",
    "nav-statement": "/webhook/nav-statement-extraction-complete",
}


def allowed_callbacks(webhook_base: str) -> dict[str, str]:
    base = webhook_base.rstrip("/")
    return {profile: base + path for profile, path in CALLBACK_PATHS.items()}


async def submit_job(
    uow: UnitOfWork, req: ExtractionJobRequest, callbacks: Mapping[str, str]
) -> ExtractionJobAccepted:
    if req.callback_url != callbacks[req.profile]:
        log.warning("extraction.callback_refused", profile=req.profile)
        raise RuleRefused(422, "CALLBACK_NOT_ALLOWED", "Callback not allowed",
                          f"Profile {req.profile} calls back only to {callbacks[req.profile]}.")
    await statements.begin_extraction(uow, req.document_id, req.profile)
    job = ExtractionJob(
        job_id=uuid.uuid4(), document_id=req.document_id, profile=req.profile, callback_url=req.callback_url,
        status="QUEUED", error=None, callback_acked=False, created_at=uow.now, finished_at=None,
    )
    ExtractionRepository(uow.session).add(job)
    await jobs.enqueue(uow.session, EXTRACT_JOB, {"jobId": str(job.job_id)}, now=uow.now,
                       dedupe_key=f"{EXTRACT_JOB}:{job.job_id}")
    uow.audit.record("extraction.submitted", "extraction-job", str(job.job_id),
                     {"documentId": str(req.document_id), "profile": req.profile})
    return ExtractionJobAccepted(job_id=job.job_id, status="QUEUED")


async def run_job(uow: UnitOfWork, payload: dict[str, Any], extractor: Extractor) -> None:
    """Jobs worker: extract the document, store the result, then queue the callback to n8n."""
    repo = ExtractionRepository(uow.session)
    job = await repo.get_for_update(uuid.UUID(payload["jobId"]))
    if job is None or job.status not in ("QUEUED", "RUNNING"):
        return
    target = await statements.extraction_target(uow, job.document_id)
    if target is None:
        raise LookupError(f"Document {job.document_id} does not exist")
    extracted = await extractor.extract(
        ExtractionRequest(job.document_id, target.object_key, job.profile, target.received_at)
    )
    await statements.write_extraction(uow, job.document_id, job.job_id, extracted)
    job.status, job.finished_at = "SUCCEEDED", uow.now
    await _queue_callback(uow, job)
    uow.audit.record("extraction.succeeded", "extraction-job", str(job.job_id),
                     {"documentId": str(job.document_id),
                      "lines": len(extracted.lines) if isinstance(extracted, ExtractedStatement) else None})


async def run_failed(uow: UnitOfWork, payload: dict[str, Any], error: str) -> None:
    """The extraction failed for good. n8n still hears about it, and raises an extraction-exception card."""
    repo = ExtractionRepository(uow.session)
    job = await repo.get_for_update(uuid.UUID(payload["jobId"]))
    if job is None or job.status not in ("QUEUED", "RUNNING"):
        return
    job.status, job.error, job.finished_at = "FAILED", error[:2000], uow.now
    await statements.extraction_failed(uow, job.document_id, error)
    await _queue_callback(uow, job)
    uow.audit.record("extraction.failed", "extraction-job", str(job.job_id),
                     {"documentId": str(job.document_id), "error": error[:200]})


async def callback_job(uow: UnitOfWork, payload: dict[str, Any], sender: CallbackSender) -> None:
    """Jobs worker: tell n8n the outcome. A refusal or timeout raises, so the job retries with backoff."""
    repo = ExtractionRepository(uow.session)
    job = await repo.get_for_update(uuid.UUID(payload["jobId"]))
    if job is None or job.callback_acked or job.status not in ("SUCCEEDED", "FAILED"):
        return
    body: dict[str, Any] = {
        "documentId": str(job.document_id), "jobId": str(job.job_id),
        "status": "succeeded" if job.status == "SUCCEEDED" else "failed",
    }
    if job.error:
        body["error"] = job.error
    await sender.send(job.callback_url, body)
    job.callback_acked = True
    uow.audit.record("extraction.callback_acked", "extraction-job", str(job.job_id), {"status": body["status"]})


async def stuck_jobs(uow: UnitOfWork, older_than_minutes: int) -> list[uuid.UUID]:
    """Extraction jobs the sweeper should re-drive (still running, or n8n never acknowledged the outcome)."""
    rows = await ExtractionRepository(uow.session).stuck(uow.now - timedelta(minutes=older_than_minutes))
    return [job.job_id for job in rows]


async def redrive_job(uow: UnitOfWork, job_id: uuid.UUID, attempt: int) -> None:
    """Queue the step a stuck job is waiting for again: the extraction itself, or the callback to n8n."""
    job = await ExtractionRepository(uow.session).get_for_update(job_id)
    if job is None:
        return
    kind = EXTRACT_JOB if job.status in ("QUEUED", "RUNNING") else CALLBACK_JOB
    if kind == EXTRACT_JOB:
        job.status = "QUEUED"
    await jobs.enqueue(uow.session, kind, {"jobId": str(job.job_id)}, now=uow.now,
                       dedupe_key=f"{kind}:{job.job_id}:redrive-{attempt}",
                       max_attempts=CALLBACK_ATTEMPTS if kind == CALLBACK_JOB else jobs.DEFAULT_MAX_ATTEMPTS)
    uow.audit.record("extraction.redriven", "extraction-job", str(job.job_id), {"step": kind, "attempt": attempt})


async def _queue_callback(uow: UnitOfWork, job: ExtractionJob) -> None:
    await jobs.enqueue(uow.session, CALLBACK_JOB, {"jobId": str(job.job_id)}, now=uow.now,
                       dedupe_key=f"{CALLBACK_JOB}:{job.job_id}", max_attempts=CALLBACK_ATTEMPTS)
