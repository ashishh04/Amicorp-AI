# n8n workflows

n8n only orchestrates. Rules, card state and audit live in the Platform API (`$vars.PLATFORM_API_URL`).
Engine execution logs are telemetry, not the audit record.

## Import order

1. `Platform Error Handler/Error-handler.json` — import with the CLI so its fixed ID is kept:
   `n8n import:workflow --input="Platform Error Handler/Error-handler.json"`.
   Every other workflow points `settings.errorWorkflow` at `AmiErrHandler001`. If you import through the UI instead,
   re-select the error workflow in each workflow's settings.
2. All other workflows.
3. Bind credentials (none are stored in the JSON): one Header Auth credential per inbound webhook group
   (intake, extraction callback, data-platform events) and one for the Platform API.

## n8n variables

| Variable | Purpose |
|---|---|
| `PLATFORM_API_URL` | Platform API base URL |
| `N8N_WEBHOOK_BASE` | Base URL the extraction service calls back on |
| `OPS_ALERT_WEBHOOK_URL` | Teams workflow webhook, used only when the Platform API itself is unreachable |
| `UC4_MAX_NEW_CARDS_PER_RUN`, `UC5_MAX_NEW_CARDS_PER_RUN` | Card cap per scan (default 200) |
| `REDRIVE_AFTER_MINUTES`, `REDRIVE_MAX_ATTEMPTS` | Sweeper thresholds (default 30 / 3) |

## Inbound webhooks (`{N8N_WEBHOOK_BASE}/webhook/<path>`)

| Path | Workflow | Called by |
|---|---|---|
| `bank-statement-received` | Bank statement processing | Intake (new statement uploaded) |
| `bank-statement-extraction-complete` | Bank statement processing | Extraction service callback |
| `nav-statement-received` | NAV statement validation | Intake (new NAV statement) |
| `nav-statement-extraction-complete` | NAV statement validation | Extraction service callback |
| `transaction-received` | Transaction monitoring (AML) | Transaction source |
| `bronze-load-completed` | Discrepancy detection | Data platform (bronze layer loaded) |
| `gold-refresh-completed` | Violation-triggered cards | Data platform (gold layer refreshed) |

## Conventions

- **Durable intake before acknowledgement.** Intake webhooks reply 202 only after the item is registered. If the
  run fails before that, the caller gets a 5xx and must retry. Malformed requests get a 400.
- **Every POST carries an `Idempotency-Key`.** Gate evaluations are keyed per execution (so a node retry does not
  re-screen); cards are keyed by business identity (document + extraction job, transaction, dedupe key).
- **Fail closed.** UC2 gates route explicit outcomes only. An unexpected outcome or a gate error raises an
  `aml.gate-exception` card with `blocksTransaction: true` — never "file as below threshold".
- **Long scans are async** (submit, poll, fetch findings), never one long synchronous HTTP call.

## Platform API contract these workflows assume

| Endpoint | Must return / guarantee |
|---|---|
| `POST /v1/bank-statements`, `POST /v1/nav-statements` | `{ statementId }`; idempotent on `objectKey` |
| `POST /v1/extraction/jobs` | Calls back with `{ documentId, jobId, status, error? }`; `status = "succeeded"` on success |
| `POST /v1/transactions` | Durable intake record; idempotent on `transactionId` |
| `POST /v1/payment-requests/claim` | `{ items: [{ transactionId, source }] }`, leased so overlapping polls cannot double-claim |
| `POST /v1/transactions/enrich` | Echoes `transactionId` |
| `POST /v1/transactions/{transactionId}/file` | Files a transaction that gate 1 marked `below-threshold` (no further monitoring) |
| `POST /v1/gates/evaluate` | `{ runId, outcome, rulesetVersion }`. Outcomes: `aml.gate1-entry` → `monitor` \| `below-threshold`; `aml.gate2-profile` → `match` \| `mismatch` (LLM uncertainty must map to `mismatch`); `aml.gate3-risk` → `clear` \| `alert`; `nav.checks` → `pass` \| anything else = exception |
| `POST /v1/scans`, `GET /v1/scans/{id}`, `GET /v1/scans/{id}/findings` | `{ scanId }`; `status` ∈ `queued` \| `running` \| `completed` \| `failed`; findings capped at `maxNewFindings`, each with `findingId`, `subjectId`, `dedupeKey` (+ `policyId` for UC5) |
| `POST /v1/cards` | `{ cardId, created }`; `created = false` on idempotent replay |
| `POST /v1/incidents` | `{ incidentId }` |
| `POST /v1/maintenance/redrive` | Re-drives stuck intake/extraction items; returns `{ sweepId, escalatedCount }` |

Holding a UC2 payment in 5 Series until a card clears it is the Platform API's job, triggered by `blocksTransaction: true`.

## Not yet built

The Platform API now handles card decisions (Approve / Reject / Return-to-AI / Delegate) and the write-back
that follows (5 Series hold, release and freeze; Valuefy publication for UC3), against stand-ins until the real
connectors exist. Still to build: SLA escalation, UC2 re-validation from gate 2 after a profile update (the
payment stays held until then), MLRO follow-through (incident, STR pack), UC1 output generation (exchange
folders) and handoff into UC2, UC6.
