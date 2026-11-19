"""FastAPI app factory. Only wiring here: no business logic."""
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import LOCAL_ENVIRONMENTS, Settings, get_settings
from app.core.dev_auth import DevSigner
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.security import TokenValidator
from app.db.session import make_engine, require_selector_loop
from app.modules.audit_log.router import router as audit_router
from app.modules.bank_statements.router import router as bank_statements_router
from app.modules.cards.router import router as cards_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.events.router import router as events_router
from app.modules.extraction.router import router as extraction_router
from app.modules.gates.router import router as gates_router
from app.modules.gates.router import rulesets_router
from app.modules.identity.dev_router import router as dev_sign_in_router
from app.modules.identity.router import router as identity_router
from app.modules.incidents.router import router as incidents_router
from app.modules.lookups.router import router as lookups_router
from app.modules.maintenance.router import router as maintenance_router
from app.modules.nav_statements.router import router as nav_statements_router
from app.modules.notifications.router import router as notifications_router
from app.modules.scans.router import router as scans_router
from app.modules.statements.router import router as statements_router
from app.modules.transaction_monitoring.router import router as transaction_monitoring_router
from app.shared.idempotency import IdempotencyStore

log = structlog.get_logger()

READY_TIMEOUT_SECONDS = 1.0


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    local = settings.environment in LOCAL_ENVIRONMENTS

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        require_selector_loop()
        engine = make_engine(settings)
        redis = Redis.from_url(
            settings.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5, health_check_interval=30
        )
        app.state.engine = engine
        app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
        app.state.redis = redis
        # Local sign-in keys live only in this process: a restart signs everyone out.
        app.state.dev_signer = DevSigner() if local else None
        app.state.token_validator = TokenValidator(settings, dev_signer=app.state.dev_signer)
        app.state.idempotency = IdempotencyStore(redis)

        stop_worker, worker = asyncio.Event(), None
        if settings.embedded_worker:  # local only (Settings refuses it elsewhere)
            from app.workers.jobs import build_handlers, run_forever

            worker = asyncio.create_task(
                run_forever(app.state.session_factory, build_handlers(settings), stop_worker)
            )
        log.info("api.started", environment=settings.environment, embedded_worker=settings.embedded_worker)
        yield
        stop_worker.set()
        if worker is not None:
            await worker
        await redis.aclose()
        await engine.dispose()
        log.info("api.stopped")

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.show_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.show_docs else None,
    )
    register_exception_handlers(app)
    app.add_middleware(RequestContextMiddleware, max_body_bytes=settings.max_body_bytes)

    for router in (
        # n8n workflows
        bank_statements_router,
        transaction_monitoring_router,
        nav_statements_router,
        extraction_router,
        gates_router,
        scans_router,
        incidents_router,
        notifications_router,
        maintenance_router,
        # n8n and the portal
        cards_router,
        # the portal
        identity_router,
        statements_router,
        lookups_router,
        audit_router,
        rulesets_router,
        dashboard_router,
        events_router,
    ):
        app.include_router(router, prefix="/v1")
    if local:
        app.include_router(dev_sign_in_router, prefix="/v1")  # local sign-in: never mounted in DEV, NPR or PRD

    @app.get("/health", tags=["system"], summary="Liveness: the process is running")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["system"], summary="Readiness: PostgreSQL and Redis are reachable")
    async def ready(request: Request) -> JSONResponse:
        # External providers (World-Check, MaaS) never take part: their outage must produce hold cards,
        # not pods taken out of service (blueprint section 8).
        checks = {"database": "ok", "redis": "ok"}
        try:
            async with request.app.state.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 - any failure means not ready
            checks["database"] = "unavailable"
        try:
            await request.app.state.redis.ping()
        except (RedisError, OSError):
            checks["redis"] = "unavailable"
        ok = all(v == "ok" for v in checks.values())
        body = {"status": "ready" if ok else "not-ready", "checks": checks}
        return JSONResponse(body, status_code=200 if ok else 503)

    return app


app = create_app()
