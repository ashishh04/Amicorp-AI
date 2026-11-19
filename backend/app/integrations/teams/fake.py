"""A stand-in for Teams on a laptop: it writes the message to the log instead of sending it."""
import structlog

from app.modules.notifications.ports import OutgoingMessage

log = structlog.get_logger()


class LogOnlySender:
    async def send(self, message: OutgoingMessage) -> None:
        log.info("notification.sent_to_log", audience=message.audience, notification_event=message.event,
                 card_id=message.card_id, incident_id=message.incident_id)
