"""What a gate needs from outside: its inputs, read by the module that owns the subject.

The gate service never reads another module's tables. The router wires each ruleset to a resolver from
the owning module (UC1 and UC3: statements; UC2: transaction monitoring), so the engine stays generic and the
inputs stay where they live.
"""
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.db.session import UnitOfWork

InputValue = str | int | float | bool | None


@dataclass(frozen=True)
class ResolvedInput:
    name: str
    value: InputValue
    source: str  # where the value was read, shown with the gate run


@dataclass(frozen=True)
class Resolution:
    inputs: list[ResolvedInput]
    llm: dict[str, Any] | None = None  # gate 2: the model's interpretation and its trace, kept with the run
    screening_ref: str | None = None  # gate 3: the screening provider's case reference
    extra: dict[str, Any] = field(default_factory=dict)


Resolver = Callable[[UnitOfWork, str], Awaitable[Resolution | list[ResolvedInput]]]
AfterEvaluation = Callable[[UnitOfWork, str, str, uuid.UUID], Awaitable[None]]  # (uow, subject, outcome, run ID)


@dataclass(frozen=True)
class GateInputs:
    subject_type: str
    resolve: Resolver
    after: AfterEvaluation | None = None  # runs in the same transaction as the gate run, e.g. a payment hold
