"""The document extraction service (layout, OCR, fields and confidence on the GPU node)."""
from app.core.config import Settings
from app.modules.extraction.ports import Extractor


def extractor(settings: Settings) -> Extractor:
    if settings.integrations == "fake":
        from app.integrations.extractor.fake import FakeExtractor

        return FakeExtractor()
    raise NotImplementedError("The extraction service is not built yet; set INTEGRATIONS=fake locally.")
