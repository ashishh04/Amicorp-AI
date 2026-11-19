"""Business rules for scans. No HTTP or SQL here.

A scan is asynchronous (README: long scans are submit, poll, fetch). The request queues it; the jobs
worker reads the data lake, keeps every candidate as a finding, and marks as new only those whose dedupe
key has no card yet. n8n then fetches the new findings, at most maxNewFindings of them.
"""
import uuid
from typing import Any

import structlog

from app.core.errors import Conflict, NotFound
from app.db.session import UnitOfWork
from app.modules.cards import service as cards
from app.modules.scans.models import Finding, Scan
from app.modules.scans.ports import ScanSource
from app.modules.scans.repository import ScanRepository
from app.modules.scans.schemas import FindingsPage, FindingView, ScanAccepted, ScanCreate, ScanView
from app.shared import jobs

log = structlog.get_logger()

SCAN_JOB = "scan.run"


class ScanNotComplete(Conflict):
    code, title = "SCAN_NOT_COMPLETE", "The scan has not completed"


async def submit_scan(uow: UnitOfWork, cmd: ScanCreate) -> ScanAccepted:
    scan = Scan(
        scan_id=uuid.uuid4(), ruleset_key=cmd.ruleset, layer=cmd.layer, batch_date=cmd.batch_date,
        scan_window=cmd.scan_window, max_new_findings=cmd.max_new_findings, status="queued",
        findings_total=None, findings_new=None, error=None, created_at=uow.now, started_at=None, finished_at=None,
    )
    await ScanRepository(uow.session).add(scan)
    await jobs.enqueue(
        uow.session, SCAN_JOB, {"scanId": str(scan.scan_id)}, now=uow.now,
        dedupe_key=f"{SCAN_JOB}:{scan.scan_id}", max_attempts=3,
    )
    uow.audit.record("scan.queued", "scan", str(scan.scan_id), {
        "ruleset": cmd.ruleset, "layer": cmd.layer, "maxNewFindings": cmd.max_new_findings,
        "batchDate": cmd.batch_date.isoformat() if cmd.batch_date else None, "scanWindow": cmd.scan_window,
    })
    return ScanAccepted(scan_id=scan.scan_id, status="queued")


async def get_scan(uow: UnitOfWork, scan_id: uuid.UUID) -> ScanView:
    async with uow:
        scan = await _scan_or_404(ScanRepository(uow.session), scan_id)
        return ScanView(
            scan_id=scan.scan_id, ruleset=scan.ruleset_key, layer=scan.layer, status=scan.status,  # type: ignore[arg-type]
            batch_date=scan.batch_date, scan_window=scan.scan_window, max_new_findings=scan.max_new_findings,
            findings_total=scan.findings_total, findings_new=scan.findings_new, error=scan.error,
            created_at=scan.created_at, finished_at=scan.finished_at,
        )


async def get_findings(uow: UnitOfWork, scan_id: uuid.UUID) -> FindingsPage:
    async with uow:
        repo = ScanRepository(uow.session)
        scan = await _scan_or_404(repo, scan_id)
        if scan.status != "completed":
            raise ScanNotComplete(f"The scan is {scan.status}; fetch findings once it is completed")
        findings = await repo.new_findings(scan_id, scan.max_new_findings)
        return FindingsPage(
            scan_id=scan_id,
            findings=[FindingView.model_validate(f, from_attributes=True) for f in findings],
            truncated=(scan.findings_new or 0) > scan.max_new_findings,
        )


async def run_scan_job(uow: UnitOfWork, payload: dict[str, Any], source: ScanSource) -> None:
    """Jobs worker: read the candidates and record the findings, marking the new ones."""
    repo = ScanRepository(uow.session)
    scan = await repo.get_for_update(uuid.UUID(payload["scanId"]))
    if scan is None or scan.status in ("completed", "failed"):
        return
    candidates = await source.candidates(scan.ruleset_key, scan.layer, scan.batch_date, scan.scan_window)
    keys = {c.dedupe_key(scan.ruleset_key) for c in candidates}
    already_carded = await cards.existing_card_keys(uow, keys)

    seen: set[str] = set()
    new_rank = 0
    for candidate in candidates:
        key = candidate.dedupe_key(scan.ruleset_key)
        is_new = key not in already_carded and key not in seen
        seen.add(key)
        new_rank += is_new
        repo.add_finding(Finding(
            finding_id=uuid.uuid4(), scan_id=scan.scan_id, rule_id=candidate.rule_id,
            subject_id=candidate.subject_id, dedupe_key=key, policy_id=candidate.policy_id, title=candidate.title,
            detail=candidate.detail, is_new=is_new, new_rank=new_rank if is_new else None,
        ))
    scan.status, scan.started_at, scan.finished_at = "completed", scan.started_at or uow.now, uow.now
    scan.findings_total, scan.findings_new = len(candidates), new_rank
    uow.audit.record("scan.completed", "scan", str(scan.scan_id), {
        "findingsTotal": scan.findings_total, "findingsNew": scan.findings_new,
    })
    log.info("scan.completed", scan_id=str(scan.scan_id), findings_total=scan.findings_total,
             findings_new=scan.findings_new)


async def fail_scan_job(uow: UnitOfWork, payload: dict[str, Any], error: str) -> None:
    """The scan failed for good: report `failed`, so the workflow stops polling and raises an incident."""
    scan = await ScanRepository(uow.session).get_for_update(uuid.UUID(payload["scanId"]))
    if scan is None or scan.status in ("completed", "failed"):
        return
    scan.status, scan.finished_at, scan.error = "failed", uow.now, "The data source could not be read"
    uow.audit.record("scan.failed", "scan", str(scan.scan_id), {"error": error[:200]})


async def finding_evidence(uow: UnitOfWork, finding_id: uuid.UUID) -> dict[str, Any] | None:
    """What a card needs to know about the finding it was raised for."""
    finding = await ScanRepository(uow.session).get_finding(finding_id)
    if finding is None:
        return None
    return {
        "title": finding.title, "ruleId": finding.rule_id, "subjectId": finding.subject_id,
        "policyId": finding.policy_id, "scanId": str(finding.scan_id), "detail": finding.detail,
    }


async def _scan_or_404(repo: ScanRepository, scan_id: uuid.UUID) -> Scan:
    scan = await repo.get(scan_id)
    if scan is None:
        raise NotFound("No scan with this ID")
    return scan
