"""Name screening for gate 3: World-Check One, or Amicheck (LLD, World-Check One and Amicheck)."""
from app.core.config import Settings
from app.modules.transaction_monitoring.ports import Screening


def screening(settings: Settings) -> Screening:
    if settings.integrations == "fake":
        from app.integrations.screening.fake import FakeScreening

        return FakeScreening()
    raise NotImplementedError("The screening connector is not built yet; set INTEGRATIONS=fake locally.")
