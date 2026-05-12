"""
Collaboration status state machine.

Allowed transitions (per 009-collab-lifecycle spec §4):
  still_deciding → in_progress, completed, didnt_work_out
  in_progress    → still_deciding, completed, didnt_work_out
  completed      → (terminal — no further transitions)
  didnt_work_out → (terminal — no further transitions)
"""

from __future__ import annotations

TERMINAL_STATES: frozenset[str] = frozenset({"completed", "didnt_work_out"})

# TRANSITION_MAP[from_status] = set of valid to_status values
TRANSITION_MAP: dict[str, frozenset[str]] = {
    "still_deciding": frozenset({"in_progress", "completed", "didnt_work_out"}),
    "in_progress": frozenset({"still_deciding", "completed", "didnt_work_out"}),
    "completed": frozenset(),
    "didnt_work_out": frozenset(),
}


class InvalidTransitionError(Exception):
    """Raised when a disallowed status transition is attempted."""

    def __init__(self, from_status: str, to_status: str) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Transition from '{from_status}' to '{to_status}' is not allowed."
        )


def validate_transition(current_status: str, new_status: str) -> None:
    """
    Raise InvalidTransitionError if the transition is not permitted.
    Callers should catch this and map to HTTP 409.
    """
    allowed = TRANSITION_MAP.get(current_status, frozenset())
    if new_status not in allowed:
        raise InvalidTransitionError(current_status, new_status)


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATES
