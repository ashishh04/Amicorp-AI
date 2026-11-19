"""Governed write-back to the systems of record (CARE, 5 Series, Valuefy) after an Approve."""
from app.core.config import Settings
from app.modules.cards.ports import WriteBack


def writer(settings: Settings) -> WriteBack:
    if settings.integrations == "fake":
        from app.integrations.writeback.fake import LogOnlyWriteBack

        return LogOnlyWriteBack()
    raise NotImplementedError("Write-back to the systems of record is not built yet; set INTEGRATIONS=fake locally.")
