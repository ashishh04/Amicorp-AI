"""Local stand-in for the write-back: it logs what would be written and changes nothing outside the platform."""
import uuid
from typing import Any

import structlog

from app.db.session import UnitOfWork

log = structlog.get_logger()


class LogOnlyWriteBack:
    async def write_back(self, uow: UnitOfWork, card_type: str, subject_id: str, payload: dict[str, Any]) -> str:
        reference = f"local-{uuid.uuid4().hex[:12]}"
        log.info("writeback.logged_only", card_type=card_type, subject_id=subject_id, reference=reference)
        return reference
