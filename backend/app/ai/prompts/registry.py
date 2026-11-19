"""Versioned prompt lookup by name + version: PROMPTS["cards.propose-correction@1"].

Free-form prompts are not allowed: every model call names one of these. Each result stores the prompt's key
and sha, so it can be traced to the exact text that produced it.
"""
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from string import Template
from types import MappingProxyType

from app.ai.prompts import templates


@dataclass(frozen=True)
class Prompt:
    id: str
    version: int
    system: str
    user: str  # a string.Template

    @property
    def key(self) -> str:
        return f"{self.id}@{self.version}"

    @property
    def sha(self) -> str:
        return hashlib.sha256(f"{self.system}\x00{self.user}".encode()).hexdigest()

    def render(self, variables: Mapping[str, str]) -> str:
        """The user message. A missing variable raises KeyError: a prompt is never sent half filled."""
        return Template(self.user).substitute(variables)


_ALL = (
    Prompt("cards.assemble-and-recommend", 1, templates.CARD_SYSTEM_V1, templates.ASSEMBLE_AND_RECOMMEND_V1),
    Prompt("cards.propose-correction", 1, templates.CARD_SYSTEM_V1, templates.PROPOSE_CORRECTION_V1),
    Prompt("cards.review-evidence", 1, templates.REVIEW_SYSTEM_V1, templates.REVIEW_EVIDENCE_V1),
    Prompt("cards.assistant", 1, templates.ASSISTANT_SYSTEM_V1, templates.ASSISTANT_V1),
    Prompt("aml.gate2-profile", 1, templates.GATE2_PROFILE_SYSTEM_V1, templates.GATE2_PROFILE_V1),
    Prompt("platform.connectivity-check", 1, templates.CONNECTIVITY_SYSTEM_V1, templates.CONNECTIVITY_USER_V1),
)
PROMPTS: Mapping[str, Prompt] = MappingProxyType({p.key: p for p in _ALL})
