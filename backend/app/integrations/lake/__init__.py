"""The data lake (Bronze, Silver, Gold on OBS; serving tables in DWS)."""
from app.core.config import Settings
from app.modules.scans.ports import ScanSource


def scan_source(settings: Settings) -> ScanSource:
    if settings.integrations == "fake":
        from app.integrations.lake.fake import FakeScanSource

        return FakeScanSource()
    raise NotImplementedError("The DWS scan source is not built yet; set INTEGRATIONS=fake locally.")
