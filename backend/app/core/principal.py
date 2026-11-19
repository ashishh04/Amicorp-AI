"""Who is calling: the authenticated principal and its Entra app roles."""
import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class Role(StrEnum):
    """Entra app roles on amc-platform-api (LLD, Portal roles)."""

    MAKER = "Maker"
    CHECKER = "Checker"
    MLRO = "MLRO"
    ADMIN = "Admin"
    AUDITOR = "Auditor"
    AUTOMATION = "Automation"  # n8n only; a person can never hold it


@dataclass(frozen=True)
class Principal:
    subject: str  # Entra object ID for people, client ID for services
    kind: Literal["user", "service"]
    roles: frozenset[Role]
    token_id: str | None = None  # Entra `uti`, kept for forensics

    @property
    def actor(self) -> str:
        """The audit trail's actor: who did it, exactly."""
        return f"{'svc' if self.kind == 'service' else 'user'}:{self.subject}"

    @property
    def log_actor(self) -> str:
        """The logs' actor: services by name, people only as a hash of their object ID."""
        if self.kind == "service":
            return self.actor
        return "user:" + hashlib.sha256(self.subject.encode()).hexdigest()[:16]
