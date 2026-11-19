"""CARE (client records): the client's KYC profile, which gates 2 and 3 read."""
from app.core.config import Settings
from app.modules.transaction_monitoring.ports import ClientProfiles


def profiles(settings: Settings) -> ClientProfiles:
    if settings.integrations == "fake":
        from app.integrations.care.fake import FakeProfiles

        return FakeProfiles()
    raise NotImplementedError("The CARE connector is not built yet; set INTEGRATIONS=fake locally.")
