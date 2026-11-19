"""What notifications need from outside: a Teams sender (decision D-07: Bot Framework or webhooks)."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OutgoingMessage:
    audience: str
    event: str
    card_id: str | None
    incident_id: str | None


class NotificationSender(Protocol):
    async def send(self, message: OutgoingMessage) -> None: ...
