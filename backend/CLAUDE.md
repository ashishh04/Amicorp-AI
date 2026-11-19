# Amicorp Platform API (backend)

The API that n8n workflows call (see `../n8n-workflows/README.md` for the contract). n8n only orchestrates;
rules, card state and audit live here.

## Layout rules
- `app/modules/<name>/` holds one business capability: `router.py` (HTTP) -> `service.py` (rules) ->
  `repository.py` (DB), with `schemas.py` (Pydantic) and `models.py` (SQLAlchemy).
- Routers never touch the DB; services never import FastAPI; repositories hold no business rules.
- Modules do not import each other's repositories. Call the other module's service instead.
- The one exception: `app/modules/dashboard/` runs read-only reporting SQL across other modules' tables. It
  holds no business rules and never writes; do not copy the pattern elsewhere.
- Cross-cutting code goes in `app/shared/` (idempotency, audit, leasing), not copied into modules.
- All LLM calls go through `app/ai/llm_client.py` with a prompt from `app/ai/prompts/registry.py`.
- Tests mirror modules: `tests/unit/<module>/`, `tests/integration/<module>/`.

## Non-negotiables
- Every POST honours `Idempotency-Key`.
- Fail closed: unknown gate outcome or LLM uncertainty -> the blocking/exception outcome.
- Every state change writes an audit record.

## Adding an endpoint
- Declare exactly one permission: `_: Principal = Depends(permit(Perm.X))`. Add new permissions to the
  table in `app/core/authz.py`; it is the only place roles meet permissions.
- State-changing POST: take `cmd: IdempotentCommand = Depends(idempotent)` and return
  `await cmd.run(lambda uow: service.fn(uow, body), status_for=...)`. The service changes state, calls
  `uow.audit.record(...)` and returns a response model; the stored response commits in the same transaction.
  Portal POSTs use `idempotent_optional` (the key is accepted, not required); n8n's always need the key.
- Reads, and PATCHes guarded by `If-Match`: the service opens the unit of work itself (`async with uow:`).
- A rule an officer can break (role, team, owner, maker-checker, state, a failed check) raises
  `RuleRefused(status, code, title, detail)`: the portal shows title and detail verbatim. Compute the rule
  once as an `app.shared.action_gate.Gate`, and use it both for the portal's hint and to enforce.
- One module needs another's data: call its service. If that would import in a circle, the router passes the
  other module's function in (see `ports.py` in cards and gates).
- Request and response models extend `app.shared.schemas.ApiModel` (camelCase, unknown fields rejected).
- Raise errors from `app.core.errors`; they become RFC 9457 problem responses.
- A change the portal shows live (a card created, updated or assigned; a statement updated) also calls
  `events.publish(uow, ...)` in the same unit of work. The SSE stream reads that outbox (`ops.event_log`),
  so an event exists only if its change committed.
- Never log `event=...` as a field: structlog reserves `event` for the message.
- `tests/unit/test_route_rules.py` fails if a route has no `permit()` or a POST has no idempotency.

## Run locally
See `../dev/README.md`. On Windows start the API with `python -m app`: psycopg's async mode needs the
selector event loop. Use `127.0.0.1`, not `localhost`, in local URLs. `python -m scripts.seed` loads the
sample officers and reference data; tests sign in as them with the `sign_in` fixture.
