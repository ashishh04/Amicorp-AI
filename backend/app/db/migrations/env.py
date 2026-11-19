"""Alembic environment: runs migrations with a synchronous psycopg connection.

The application uses the async driver; migrations do not need it, and the sync driver avoids event-loop
differences between Windows and Linux.
"""
from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings
from app.db.base import Base
from app.modules.cards import models as _card_models  # noqa: F401 - registers tables on Base
from app.modules.events import models as _event_models  # noqa: F401
from app.modules.extraction import models as _extraction_models  # noqa: F401
from app.modules.gates import models as _gate_models  # noqa: F401
from app.modules.identity import models as _identity_models  # noqa: F401
from app.modules.incidents import models as _incident_models  # noqa: F401
from app.modules.lookups import models as _lookup_models  # noqa: F401
from app.modules.maintenance import models as _maintenance_models  # noqa: F401
from app.modules.notifications import models as _notification_models  # noqa: F401
from app.modules.scans import models as _scan_models  # noqa: F401
from app.modules.statements import models as _statement_models  # noqa: F401
from app.modules.transaction_monitoring import models as _transaction_models  # noqa: F401
from app.shared import models as _shared_models  # noqa: F401

target_metadata = Base.metadata


def run_migrations() -> None:
    settings = get_settings()
    engine = create_engine(
        settings.database_url.get_secret_value(),
        poolclass=pool.NullPool,
        connect_args={"options": "-c timezone=UTC", "connect_timeout": settings.db_connect_timeout_seconds},
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_schemas=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("Offline migrations are not supported; run against a database.")
run_migrations()
