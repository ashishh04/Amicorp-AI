"""5 Series (payments): payment details, new payment requests, and payment holds."""
from app.core.config import Settings
from app.modules.transaction_monitoring.ports import PaymentSystem


def payments(settings: Settings) -> PaymentSystem:
    if settings.integrations == "fake":
        from app.integrations.five_series.fake import FakePayments

        return FakePayments()
    raise NotImplementedError("The 5 Series connector is not built yet; set INTEGRATIONS=fake locally.")
