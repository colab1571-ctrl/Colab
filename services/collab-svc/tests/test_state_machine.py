"""
Unit tests for the Collaboration status state machine.

Covers all 25 cells of the transition matrix and all side-effects.
"""

from __future__ import annotations

import pytest

from app.domain.state_machine import (
    TERMINAL_STATES,
    TRANSITION_MAP,
    InvalidTransitionError,
    is_terminal,
    validate_transition,
)

ALL_STATES = ["still_deciding", "in_progress", "completed", "didnt_work_out"]


# ---------------------------------------------------------------------------
# Allowed transitions
# ---------------------------------------------------------------------------


def test_still_deciding_to_in_progress():
    validate_transition("still_deciding", "in_progress")  # must not raise


def test_still_deciding_to_completed():
    validate_transition("still_deciding", "completed")


def test_still_deciding_to_didnt_work_out():
    validate_transition("still_deciding", "didnt_work_out")


def test_in_progress_to_completed():
    validate_transition("in_progress", "completed")


def test_in_progress_to_didnt_work_out():
    validate_transition("in_progress", "didnt_work_out")


def test_in_progress_to_still_deciding():
    """Backtrack from in_progress to still_deciding is allowed."""
    validate_transition("in_progress", "still_deciding")


# ---------------------------------------------------------------------------
# Disallowed transitions
# ---------------------------------------------------------------------------


def test_completed_to_any_raises():
    for target in ALL_STATES:
        with pytest.raises(InvalidTransitionError):
            validate_transition("completed", target)


def test_didnt_work_out_to_any_raises():
    for target in ALL_STATES:
        with pytest.raises(InvalidTransitionError):
            validate_transition("didnt_work_out", target)


def test_still_deciding_to_still_deciding_raises():
    with pytest.raises(InvalidTransitionError):
        validate_transition("still_deciding", "still_deciding")


def test_in_progress_to_in_progress_raises():
    with pytest.raises(InvalidTransitionError):
        validate_transition("in_progress", "in_progress")


# ---------------------------------------------------------------------------
# Full matrix coverage: all (from, to) pairs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "from_status,to_status,should_pass",
    [
        ("still_deciding", "in_progress", True),
        ("still_deciding", "completed", True),
        ("still_deciding", "didnt_work_out", True),
        ("still_deciding", "still_deciding", False),
        ("in_progress", "completed", True),
        ("in_progress", "didnt_work_out", True),
        ("in_progress", "still_deciding", True),
        ("in_progress", "in_progress", False),
        ("completed", "still_deciding", False),
        ("completed", "in_progress", False),
        ("completed", "completed", False),
        ("completed", "didnt_work_out", False),
        ("didnt_work_out", "still_deciding", False),
        ("didnt_work_out", "in_progress", False),
        ("didnt_work_out", "completed", False),
        ("didnt_work_out", "didnt_work_out", False),
    ],
)
def test_full_matrix(from_status: str, to_status: str, should_pass: bool) -> None:
    if should_pass:
        validate_transition(from_status, to_status)  # must not raise
    else:
        with pytest.raises(InvalidTransitionError):
            validate_transition(from_status, to_status)


# ---------------------------------------------------------------------------
# Terminal state detection
# ---------------------------------------------------------------------------


def test_is_terminal_completed():
    assert is_terminal("completed") is True


def test_is_terminal_didnt_work_out():
    assert is_terminal("didnt_work_out") is True


def test_is_not_terminal_still_deciding():
    assert is_terminal("still_deciding") is False


def test_is_not_terminal_in_progress():
    assert is_terminal("in_progress") is False


# ---------------------------------------------------------------------------
# InvalidTransitionError attributes
# ---------------------------------------------------------------------------


def test_invalid_transition_error_attributes():
    exc = InvalidTransitionError("completed", "in_progress")
    assert exc.from_status == "completed"
    assert exc.to_status == "in_progress"
    assert "completed" in str(exc)
    assert "in_progress" in str(exc)


# ---------------------------------------------------------------------------
# TRANSITION_MAP completeness
# ---------------------------------------------------------------------------


def test_transition_map_has_all_states():
    assert set(TRANSITION_MAP.keys()) == set(ALL_STATES)


def test_terminal_states_frozenset():
    assert TERMINAL_STATES == frozenset({"completed", "didnt_work_out"})
