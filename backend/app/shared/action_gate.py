"""The answer to "may this person do this now?", computed once and used twice (portal contract, ActionGate).

The detail endpoints turn a Gate into the portal's hint ({allowed, reason}); the command endpoints raise
it as a problem with its status (403 role or duty, 409 state, 422 check). One function per rule computes
it, so the buttons and the API can never disagree.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Gate:
    allowed: bool
    reason: str | None = None
    status: int = 200


ALLOW = Gate(True)


def deny(status: int, reason: str) -> Gate:
    return Gate(False, reason, status)
