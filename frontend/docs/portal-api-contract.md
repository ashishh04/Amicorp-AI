# Portal API contract (platform-api ↔ portal-web)

What the Angular portal expects from `platform-api`. The TypeScript shapes are the source of
truth for field names: [`src/app/core/api/portal.models.ts`](../src/app/core/api/portal.models.ts).
The in-browser mock ([`src/app/core/mock/mock-backend.ts`](../src/app/core/mock/mock-backend.ts))
implements every endpoint and rule below, so it doubles as an executable reference; its tests are in
`mock-backend.spec.ts`.

It follows the contract-drift proposal (F5) in the backend blueprint (`docs/design/platform-api-blueprint.html`):
`/decisions`, `/audit/events`, `/statements/{id}` + `/lines`, `/card-types`, `/dashboard/*`, cursor paging and
the SSE ticket and stream.

**Source** says where each endpoint comes from: **LLD** = AMC-LLD-01 (Platform API: portal endpoints),
**LLD+** = LLD endpoint with fields the portal design adds, **New** = added by the portal design.
When platform-api publishes these in its OpenAPI spec, regenerate the client (`npm run api:gen`) and
move `PortalApi` onto it.

## Conventions

| Topic            | Rule                                                                                                                                                                                                                            |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Base path        | The portal calls `/api/v1/...`; ingress (and `proxy.conf.json` locally) strips `/api`, so the API serves `/v1/...`.                                                                                                             |
| Auth             | Entra ID bearer token (scope `api://amc-platform-api/.default`). App roles come from the `roles` claim: `Maker`, `Checker`, `MLRO`, `Admin`, `Auditor`. Local and test only: `GET /v1/dev/users` and `POST /v1/dev/sign-in` `{ userId }` → `{ accessToken, expiresIn, user }` stand in for Entra (sign-in mode `local`). |
| Errors           | RFC 9457 `application/problem+json`: `{ type, title, status, detail, instance, failures? }`. `failures[]` items are `{ message, lineNo?, field? }`. The portal shows `title` and `detail` verbatim, so write them for officers. |
| Status codes     | 401 = no valid token (the portal ends the session and asks the user to sign in again); 403 = role, team, owner or maker–checker rule; 409 = wrong state; 412 = stale `If-Match`; 422 = validation or a failed gate.            |
| Idempotency      | Every state-changing POST accepts `Idempotency-Key` (LLD, Idempotency).                                                                                                                                                         |
| Concurrency      | Statement lines carry an `etag`; `PATCH` sends it as `If-Match`.                                                                                                                                                                |
| Paging           | Lists take `limit` and `cursor` and return `{ items, nextCursor }` (`nextCursor` null on the last page), as the backend blueprint proposes for F5.                                                                              |
| Time             | UTC ISO 8601 everywhere. The portal renders it in the user's HK or EU business-hours zone (`calendar` in `/v1/me`).                                                                                                             |
| Money            | `{ amount: number, currency: string }`.                                                                                                                                                                                         |
| Permission hints | `ActionGate = { allowed: boolean, reason?: string }`. The API computes it for the caller with **the same code that enforces the rule**. The portal shows disabled buttons with `reason`; it never decides on its own.           |

## Endpoints

| Method | Path                                                       | Roles                                   | Request → response                                                                                                                                                                                                                                                                                        | Source                               |
| ------ | ---------------------------------------------------------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| GET    | `/v1/me`                                                   | all                                     | → `CurrentUser { id, displayName, email, roles[], dataScope[], teams[], calendar: 'HK'\|'EU' }`                                                                                                                                                                                                           | LLD+ (teams, calendar)               |
| GET    | `/v1/events/ticket`                                        | all                                     | → `{ ticket }`, valid for one minute                                                                                                                                                                                                                                                                      | LLD                                  |
| GET    | `/v1/events/stream?ticket&lastEventId`                     | all                                     | SSE; see [Live events](#live-events)                                                                                                                                                                                                                                                                      | LLD                                  |
| GET    | `/v1/cards?view&q&useCase&type&severity&sort&limit&cursor` | Maker, Checker, MLRO, Auditor           | → `{ items: CardSummary[], nextCursor }`. `view`: `mine`, `team`, `due-soon` (due within 4 h), `overdue`, `escalated`, `closed`; no view = every card in scope, open or closed (global search, "recently updated"). `useCase`: UC1–UC5. `sort`: `dueAt` (default) or `-updatedAt` (default for `closed`). | LLD+ (view, q, useCase)              |
| GET    | `/v1/cards/counts`                                         | Maker, Checker, MLRO, Auditor           | → `CardCounts`, one number per view                                                                                                                                                                                                                                                                       | New                                  |
| GET    | `/v1/cards/{id}`                                           | Maker, Checker, MLRO, Auditor           | → `CardDetail`: evidence, recommendation, gate runs, history, mandatory checks, `actions` (per decision), `hold`, `sla`, `calendar`, `escalationRole`, `onApproval`, `statement` progress (UC1)                                                                                                           | LLD+                                 |
| POST   | `/v1/cards/{id}/decisions`                                 | Checker, MLRO (Return-to-AI also Maker) | `{ decision: APPROVE\|REJECT\|RETURN_TO_AI\|DELEGATE, rationale, delegateTo? }` → `CardDetail`                                                                                                                                                                                                            | LLD                                  |
| GET    | `/v1/cards/{id}/delegates`                                 | Checker, MLRO                           | → `{ items: PersonRef[] }`: the people who may take this card (same deciding role, owning team, not the maker or owner). It replaces a generic user search, so eligibility stays on the server.                                                                                                           | New                                  |
| POST   | `/v1/cards/{id}/assistant`                                 | Maker, Checker, MLRO, Auditor           | `{ question, scope: 'card'\|'entities' }` → `{ answer, grounded, citations: [{ id, title, docId, page, snippet }] }`                                                                                                                                                                                      | LLD+ (scope, grounded)               |
| GET    | `/v1/statements/{id}`                                      | Maker, Checker, Auditor                 | → `StatementHeader`: balances, `extraction.threshold`, `references[]`, gate results `checks[]` (S1–S6), `editable`                                                                                                                                                                                        | New                                  |
| GET    | `/v1/statements/{id}/lines`                                | Maker, Checker, Auditor                 | → `{ items: StatementLine[] }` with per-field `confidence`, `corrected[]`, `correctedBy`, `approved`, the caller's `approve` hint, `box`, `etag`, `enNumber`                                                                                                                                              | LLD                                  |
| PATCH  | `/v1/statements/{id}/lines/{lineId}`                       | Maker                                   | `If-Match`; partial `{ valueDate, description, debit, credit, balance, enNumber }` → `StatementLine`                                                                                                                                                                                                      | LLD                                  |
| POST   | `/v1/statements/{id}/lines/{lineId}/approve`               | Maker                                   | → `StatementLine`                                                                                                                                                                                                                                                                                         | LLD                                  |
| PATCH  | `/v1/statements/{id}/references`                           | Maker                                   | `{ bankId?, accountNo?, entity? }` → `StatementHeader`                                                                                                                                                                                                                                                    | New                                  |
| POST   | `/v1/statements/{id}/submit`                               | Maker                                   | → `StatementHeader`, or 422 with every failing gate in `failures[]`                                                                                                                                                                                                                                       | LLD                                  |
| GET    | `/v1/lookups/en-numbers?q`                                 | Maker, Checker, Auditor                 | → `{ items: [{ code, name }] }` from the daily 5 Series lookup                                                                                                                                                                                                                                            | New                                  |
| GET    | `/v1/rulesets`                                             | Admin, Checker, MLRO                    | → `{ items: Ruleset[] }`; each version carries `actions.approve`; each ruleset carries `approvers` (who approves, as a phrase) and `actions.draft`                                                                                                                                                        | LLD+                                 |
| POST   | `/v1/rulesets/{key}/test`                                  | Admin, Checker, MLRO                    | `{ version, inputs }` → `{ outcome, matchedRule, trace[], version }` (no side effects)                                                                                                                                                                                                                    | New                                  |
| POST   | `/v1/rulesets/{key}/versions/{v}/approve`                  | Checker, MLRO                           | → `Ruleset`                                                                                                                                                                                                                                                                                               | LLD                                  |
| POST   | `/v1/rulesets/{key}/validate`                              | Admin                                   | `{ rules }` → `RulesetValidation { valid, errors[], regression[] }`: schema, outcomes, catch-all last, regression cases                                                                                                                                                                                   | New (LLD version cut)                |
| POST   | `/v1/rulesets/{key}/versions`                              | Admin                                   | `RulesetDraft { basedOn, note, rules }` → `Ruleset` with the new draft; 409 if a draft exists                                                                                                                                                                                                             | LLD ("Admin drafts")                 |
| PUT    | `/v1/rulesets/{key}/versions/{v}`                          | Admin                                   | `RulesetDraft` → `Ruleset`; drafts only; the editor becomes the drafter                                                                                                                                                                                                                                   | New                                  |
| DELETE | `/v1/rulesets/{key}/versions/{v}`                          | Admin                                   | → `Ruleset` without the draft; drafts only                                                                                                                                                                                                                                                                | New                                  |
| GET    | `/v1/audit/events?q&entity&actor&since&limit&cursor`       | Auditor, MLRO                           | → `{ items: AuditEvent[], nextCursor }`, newest first, each with `domain: 'AML'\|'General'`                                                                                                                                                                                                               | LLD+                                 |
| GET    | `/v1/dashboard/summary?days`                               | Checker, MLRO, Admin                    | `days` 7, 14, 30 or 90 → `KpiSummary` (HLD service indicators), with per-day `series` and `previous`-period values for each KPI                                                                                                                                                                           | New (the blueprint's `/dashboard/*`) |
| GET    | `/v1/card-types`                                           | Admin                                   | → `{ items: CardType[] }`                                                                                                                                                                                                                                                                                 | New                                  |
| GET    | `/v1/settings/data-scope`                                  | Admin                                   | → `{ items: DataScopeGroup[] }`                                                                                                                                                                                                                                                                           | New                                  |

## Rules the API enforces (the portal only mirrors them)

**Who sees which cards.** The owning team decides it: Makers and Checkers see their teams' cards. The MLRO
sees every `aml.*` card, Auditors see everything, and Admins see no cards. A card outside scope returns 403.

**Decisions** (`POST /decisions`), checked in this order:

1. The card must be `AWAITING_DECISION`, otherwise 409.
2. The caller must hold the deciding role:
   - `aml.mlro-escalation`: the MLRO only;
   - other `aml.*` cards: a Checker in the team, or the MLRO;
   - everything else: a Checker in the team.
3. The caller must be the card's owner (or its delegate). Otherwise 403.
4. Maker–checker: the card's maker cannot Approve or Reject, even if they also hold Checker. They can delegate.
5. Approve requires every mandatory check to be met (UC1: the statement is submitted). Otherwise 422.
6. `rationale` is mandatory for every decision (at least 3 characters; the column is `NOT NULL`). Otherwise 422.
7. Return-to-AI is open to Makers and Checkers of the team and to the MLRO. A 4th return escalates the card.
8. Delegate goes only to someone from `/delegates`, at most twice per card.

**Statements.**

- Only a Maker in the owning team can edit, and only while `IN_REVIEW`.
- A stale `If-Match` returns 412.
- EN numbers must exist in today's lookup table (422).
- A line with an uncorrected field below `extraction.threshold` cannot be approved (422).
- `submit` runs gates S1–S6: dates in period, debit xor credit, running balance, closing balance, references valid, every line approved. The submit is a hard stop on any failure.
- Correcting, approving or submitting records the caller as the card's maker.

**Rulesets.**

- Admins draft. A draft is checked before it is saved: unique rule IDs, a description for every rule, outcomes from the ruleset's list, known operators only, and a catch-all (`when: true`) as the last rule. The regression results are returned with it. A ruleset has at most one draft (409), and every edit records the editor as the drafter.
- Only drafts can be approved (409).
- `aml.*` versions are approved by the MLRO. Other versions by the MLRO or a Checker of the owning team.
- Admins draft but never approve.
- The drafter cannot approve (four eyes).
- Every regression case must give its expected outcome (422).

**Audit.** Auditors see everything; the MLRO sees only `domain = AML`.

**Auditors.** Every non-GET returns 403.

## Live events

`GET /v1/events/stream` sends typed events (`event: card.updated`) with a small JSON payload. The portal
re-reads the REST resource, so payloads never carry sensitive detail.

| Type                | Payload                        | Portal reaction                                                                                                  |
| ------------------- | ------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| `card.created`      | `{ cardId, state, title? }`    | Refreshes the inbox and counts; notification and toast                                                           |
| `card.updated`      | `{ cardId, state, title? }`    | Refreshes the card if open, the inbox and counts; notification for ready, escalated, closed or write-back failed |
| `card.assigned`     | `{ cardId, assignee, title? }` | Toast when `assignee` is the caller                                                                              |
| `statement.updated` | `{ statementId, cardId }`      | Refreshes the open workspace                                                                                     |

`title` is optional; without it the notification shows the card ID.
