"""Business rules for notifications. No HTTP or SQL here.

A request only queues the notification, together with a delivery job in the same transaction. The jobs
worker delivers it to Teams (decision D-07), so a slow or failing Teams call never fails or slows the
workflow that asked for it. Delivery is at-least-once: a crash between sending and committing can send
a message twice, which is acceptable for a notification.
"""
import uuid
from typing import Any

import structlog

from app.db.session import UnitOfWork
from app.modules.notifications.models import Notification
from app.modules.notifications.ports import NotificationSender, OutgoingMessage
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import NotificationCreate, NotificationQueued
from app.shared import jobs

log = structlog.get_logger()

DELIVER_JOB = "notification.deliver"


async def queue_notification(uow: UnitOfWork, cmd: NotificationCreate) -> NotificationQueued:
    notification = Notification(
        notification_id=uuid.uuid4(), audience=cmd.audience, channel=cmd.channel, event=cmd.event,
        card_id=cmd.card_id, incident_id=cmd.incident_id,
        payload=cmd.model_dump(
            mode="json", by_alias=True, exclude_none=True,
            include={"fallback_audience", "digest", "sweep_id", "escalated_count"},
        ),
        status="QUEUED", attempts=0, created_at=uow.now, sent_at=None,
    )
    await NotificationRepository(uow.session).add(notification)
    await jobs.enqueue(
        uow.session, DELIVER_JOB, {"notificationId": str(notification.notification_id)},
        now=uow.now, dedupe_key=f"{DELIVER_JOB}:{notification.notification_id}",
    )
    uow.audit.record("notification.queued", "notification", str(notification.notification_id), {
        "audience": cmd.audience, "event": cmd.event,
        "cardId": str(cmd.card_id) if cmd.card_id else None,
        "incidentId": str(cmd.incident_id) if cmd.incident_id else None,
    })
    # structlog reserves `event` for the log message itself, so the notification's event is notification_event.
    log.info("notification.queued", notification_id=str(notification.notification_id),
             notification_event=cmd.event, audience=cmd.audience)
    return NotificationQueued(notification_id=notification.notification_id, status="QUEUED")


async def deliver_job(uow: UnitOfWork, payload: dict[str, Any], sender: NotificationSender) -> None:
    """Jobs worker: send one queued notification."""
    repo = NotificationRepository(uow.session)
    notification = await repo.get_for_update(uuid.UUID(payload["notificationId"]))
    if notification is None or notification.status != "QUEUED":
        return
    notification.attempts += 1
    await sender.send(OutgoingMessage(
        audience=notification.audience, event=notification.event,
        card_id=str(notification.card_id) if notification.card_id else None,
        incident_id=str(notification.incident_id) if notification.incident_id else None,
    ))
    notification.status, notification.sent_at = "SENT", uow.now
    uow.audit.record("notification.sent", "notification", str(notification.notification_id), {
        "channel": notification.channel,
    })
