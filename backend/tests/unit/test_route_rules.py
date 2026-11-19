"""Rules every route must follow, checked by walking the app's route table (blueprint section 4)."""
from collections.abc import Iterator

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, iter_route_contexts

from app.core.authz import PERM_MARKER
from app.main import app
from app.shared.idempotency import idempotency_context, optional_idempotency_context

# Local sign-in: mounted only in local and test, and nobody is signed in yet when it is called.
LOCAL_ONLY = "/v1/dev/"


def calls(dependant: Dependant) -> Iterator[object]:
    for dep in dependant.dependencies:
        yield dep.call
        yield from calls(dep)


def v1_routes() -> list[tuple[str, set[str], APIRoute]]:
    """Every route under /v1. FastAPI 0.143 keeps included routers lazy, so walk them the way OpenAPI does."""
    found = []
    for ctx in iter_route_contexts(app.routes):
        route, path = ctx.original_route, ctx.path or ""
        if isinstance(route, APIRoute) and path.startswith("/v1") and not path.startswith(LOCAL_ONLY):
            found.append((path, set(ctx.methods or ()), route))
    return found


def test_there_are_v1_routes():
    paths = {path for path, _, _ in v1_routes()}
    assert {"/v1/incidents", "/v1/notifications", "/v1/cards/{card_id}/decisions", "/v1/statements/{statement_id}",
            "/v1/audit/events", "/v1/bank-statements", "/v1/extraction/jobs", "/v1/gates/evaluate",
            "/v1/rulesets", "/v1/dashboard/summary", "/v1/events/ticket", "/v1/events/stream",
            "/v1/cards/{card_id}/assistant", "/v1/transactions", "/v1/nav-statements",
            "/v1/maintenance/redrive"} <= paths


def test_every_v1_route_declares_a_permission():
    missing = [f"{sorted(methods)} {path}" for path, methods, route in v1_routes()
               if not any(hasattr(c, PERM_MARKER) for c in calls(route.dependant))]
    assert not missing, f"Routes without permit(): {missing}"


def test_every_v1_post_handles_an_idempotency_key():
    accepted = {idempotency_context, optional_idempotency_context}
    missing = [path for path, methods, route in v1_routes()
               if "POST" in methods and not accepted & set(calls(route.dependant))]
    assert not missing, f"POST routes without Idempotency-Key handling: {missing}"


def test_routes_n8n_calls_require_the_key():
    """n8n retries every node, so its POSTs must not run without a key (the portal's may)."""
    for path in ("/v1/cards", "/v1/bank-statements", "/v1/extraction/jobs", "/v1/gates/evaluate",
                 "/v1/nav-statements", "/v1/transactions", "/v1/transactions/enrich", "/v1/payment-requests/claim",
                 "/v1/transactions/{transaction_id}/file", "/v1/maintenance/redrive"):
        route = next(r for p, m, r in v1_routes() if p == path and "POST" in m)
        assert idempotency_context in set(calls(route.dependant)), path


def test_the_local_sign_in_is_mounted_only_locally():
    from app.core.config import Settings
    from app.main import create_app

    dev = Settings(  # type: ignore[call-arg]
        _env_file=None, environment="dev", database_url="postgresql+psycopg://x@127.0.0.1/x",
        entra_tenant_id="t", entra_api_client_id="c", automation_dev_token=None, integrations="real",
        maas_integration=None, embedded_worker=False,
    )
    paths = {ctx.path for ctx in iter_route_contexts(create_app(dev).routes)}
    assert "/v1/dev/sign-in" not in paths
    assert "/v1/dev/sign-in" in {ctx.path for ctx in iter_route_contexts(app.routes)}
