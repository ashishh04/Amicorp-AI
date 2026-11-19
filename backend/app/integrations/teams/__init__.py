"""Microsoft Teams notifications (decision D-07)."""
from app.core.config import Settings
from app.modules.notifications.ports import NotificationSender


def sender(settings: Settings) -> NotificationSender:
    if settings.integrations == "fake":
        from app.integrations.teams.fake import LogOnlySender

        return LogOnlySender()
    raise NotImplementedError("The Teams sender is not built yet (D-07); set INTEGRATIONS=fake locally.")
