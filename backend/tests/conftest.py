"""Shared fixtures: test settings, the test database, and an in-process HTTP client for the app.

Integration tests need the containers from dev/docker-compose.yml. Without them they are skipped.
"""
import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from psycopg import sql

BACKEND = Path(__file__).resolve().parents[1]
TEST_DB = "amicorp_test"
DEV_TOKEN = "test-automation-token-0123456789-abcdefghij"
AUTH = {"Authorization": f"Bearer {DEV_TOKEN}"}

# Set before anything imports app.*: environment variables win over backend/.env.
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", f"postgresql+psycopg://amc:amc_local_only@127.0.0.1:5440/{TEST_DB}"
)
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://127.0.0.1:6379/15")
os.environ["AUTOMATION_DEV_TOKEN"] = DEV_TOKEN
os.environ["INTEGRATIONS"] = "fake"
os.environ["MAAS_INTEGRATION"] = "fake"  # never the real model, whatever backend/.env says
os.environ["EMBEDDED_WORKER"] = "false"  # tests run jobs explicitly with the run_jobs fixture


def libpq_url(sqlalchemy_url: str) -> str:
    return sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture
def anyio_backend() -> tuple[str, dict[str, object]]:
    # psycopg's async mode needs the selector loop (the default on Linux, not on Windows).
    return "asyncio", {"loop_factory": asyncio.SelectorEventLoop}


@pytest.fixture(scope="session")
def database() -> Iterator[str]:
    url = libpq_url(os.environ["DATABASE_URL"])
    admin_url = url.rsplit("/", 1)[0] + "/postgres"
    try:
        with psycopg.connect(admin_url, autocommit=True, connect_timeout=3) as conn:
            if conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone() is None:
                conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DB)))
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL is not reachable. Start it with: docker compose -f dev/docker-compose.yml up -d")

    from alembic import command
    from alembic.config import Config

    from scripts.seed import seed

    command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
    seed(url)  # the sample officers, lookups and rulesets; clean_db puts the rulesets back before each test
    yield url


@pytest.fixture
def clean_db(database: str) -> Iterator[str]:
    from scripts.seed import reset_rulesets

    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute(
            "TRUNCATE ops.idempotency_key, ops.incident, ops.notification, ops.job, ops.extraction_job, "
            "ops.event_log, ops.redrive, rules.finding, rules.scan, rules.gate_run, stmt.statement_line, "
            "stmt.nav_detail, stmt.statement, txn.transaction, txn.payment_request, "
            "card.card_evidence, card.card_event, card.card, audit.audit_event"
        )
        conn.execute(
            "UPDATE audit.chain_head SET last_seq = 0, last_hash = decode(repeat('00', 32), 'hex') "
            "WHERE chain_id = 0"
        )
    reset_rulesets(database)  # ruleset tests draft and approve versions
    try:
        import redis

        redis.Redis.from_url(os.environ["REDIS_URL"], socket_timeout=1).flushdb()
    except Exception:  # noqa: S110 - Redis is optional: idempotency falls back to the database
        pass
    yield database


@pytest.fixture
async def app(clean_db: str) -> AsyncIterator[object]:
    from app.main import create_app

    application = create_app()
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: object) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


class RecordingCallbacks:
    """Stands in for n8n's extraction webhook: records each callback, and can refuse them."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []
        self.refuse = False

    async def send(self, url: str, body: dict[str, Any]) -> None:
        if self.refuse:
            raise RuntimeError("n8n answered the callback with HTTP 503")
        self.sent.append((url, body))


@pytest.fixture
def callbacks() -> RecordingCallbacks:
    return RecordingCallbacks()


@pytest.fixture
def sign_in(client: httpx.AsyncClient) -> Callable[[str], Awaitable[dict[str, str]]]:
    """Sign in as a sample officer through the local sign-in, e.g. `await sign_in("u-priya")`."""
    from app.modules.identity.personas import persona_id

    async def _sign_in(handle: str) -> dict[str, str]:
        response = await client.post("/v1/dev/sign-in", json={"userId": str(persona_id(handle))})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['accessToken']}"}

    return _sign_in


@pytest.fixture
def run_jobs(app: Any, callbacks: RecordingCallbacks) -> Callable[[], Awaitable[int]]:
    """Run queued jobs until none are due, as the jobs worker would. Returns how many ran."""
    from app.core.config import get_settings
    from app.workers.jobs import build_handlers, run_due_jobs

    handlers = build_handlers(get_settings(), callbacks=callbacks)

    async def _run() -> int:
        total = 0
        for _ in range(20):
            leased = await run_due_jobs(app.state.session_factory, handlers, worker="test-worker")
            total += leased
            if leased == 0:
                break
        return total

    return _run
