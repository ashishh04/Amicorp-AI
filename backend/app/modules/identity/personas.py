"""The local users: the portal's sample officers (frontend mock-personas.ts), with stable UUIDs.

scripts/seed.py loads them in local and test only. DEV, NPR and PRD read people from Entra ID.
"""
import uuid
from dataclasses import dataclass

_NAMESPACE = uuid.UUID("6f1c3b52-9d0e-4b5a-8f3e-2a6c1d7e9b40")


def persona_id(handle: str) -> uuid.UUID:
    """The UUID a sample officer always has, e.g. persona_id("u-priya")."""
    return uuid.uuid5(_NAMESPACE, handle)


@dataclass(frozen=True)
class Persona:
    handle: str
    display_name: str
    email: str
    roles: tuple[str, ...]
    teams: tuple[str, ...]
    calendar: str
    data_scope: tuple[str, ...]

    @property
    def user_id(self) -> uuid.UUID:
        return persona_id(self.handle)


PERSONAS: tuple[Persona, ...] = (
    Persona("u-chan", "Chan Tai Man", "tm.chan@amicorp.example", ("Maker",), ("Operations",), "HK",
            ("HK client book",)),
    Persona("u-priya", "Priya Lam", "p.lam@amicorp.example", ("Checker",), ("Operations",), "HK",
            ("HK client book",)),
    Persona("u-ahmed", "Ahmed Khan", "a.khan@amicorp.example", ("Checker",), ("Operations",), "HK",
            ("HK client book",)),
    Persona("u-kenneth", "Kenneth Ho", "k.ho@amicorp.example", ("Checker",), ("Compliance",), "HK",
            ("All AML-monitored clients",)),
    Persona("u-ava", "Ava Leung", "a.leung@amicorp.example", ("Checker",), ("Compliance",), "HK",
            ("All AML-monitored clients",)),
    Persona("u-daniel", "Daniel Wong", "d.wong@amicorp.example", ("MLRO",), ("MLRO office",), "HK",
            ("All AML-monitored clients",)),
    Persona("u-sofia", "Sofia Rossi", "s.rossi@amicorp.example", ("Maker",), ("Fund accounting",), "EU",
            ("Administered funds",)),
    Persona("u-lars", "Lars Jansen", "l.jansen@amicorp.example", ("Checker",), ("Fund accounting",), "EU",
            ("Administered funds",)),
    Persona("u-meiling", "Mei Ling Tan", "ml.tan@amicorp.example", ("Maker", "Checker"), ("Data team",), "HK",
            ("All entities (data stewardship)",)),
    Persona("u-ravi", "Ravi Menon", "r.menon@amicorp.example", ("Checker",), ("Data team",), "HK",
            ("All entities (data stewardship)",)),
    Persona("u-grace", "Grace Lee", "g.lee@amicorp.example", ("Admin",), ("Platform",), "HK", ()),
    Persona("u-martin", "Martin de Vries", "m.devries@amicorp.example", ("Auditor",), ("Internal audit",), "EU",
            ("All entities (read only)",)),
)
