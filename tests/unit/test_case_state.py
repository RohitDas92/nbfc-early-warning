from datetime import date
from typing import get_args

import pytest

from nbfc_ews.domain.case_state import _TRANSITIONS, InvalidTransition, apply_event
from nbfc_ews.domain.models import Case, CaseState, Event, EventType

VALID_STATES = set(get_args(CaseState))
VALID_EVENTS = set(get_args(EventType))


def test_transition_table_uses_only_valid_names():
    bad = []
    for (state, event), new_state in _TRANSITIONS.items():
        if state not in VALID_STATES:
            bad.append(f"bad from-state: {state!r}")
        if event not in VALID_EVENTS:
            bad.append(f"bad event: {event!r}")
        if new_state not in VALID_STATES:
            bad.append(f"bad to-state: {new_state!r}")
    assert not bad, "\n".join(bad)

def test_investigation_started_moves_case_to_investigating():
    case = Case(case_id="EWS-001", state="open", case_type="bounce_pattern")

    result = apply_event(case, Event(type="investigation_started", at=date(2026, 9, 11)))

    assert result.state == "investigating"

def test_closing_without_outcome_is_refused():
    case = Case(case_id="EWS-001", state="awaiting_review", case_type="bounce_pattern")

    with pytest.raises(InvalidTransition):
        apply_event(case, Event(type="closed", at=date(2026, 9, 11)))

def test_closing_records_outcome_and_date():
    case = Case(case_id="EWS-001", state="awaiting_review", case_type="bounce_pattern")

    result = apply_event(
        case,
        Event(type="closed", at=date(2026, 9, 11), outcome="recovered"),
    )

    assert result.state == "closed"
    assert result.outcome == "recovered"
    assert result.closed_at == date(2026, 9, 11)

def test_snooze_records_snoozed_until():
    case = Case(case_id="EWS-001", state="awaiting_review", case_type="bounce_pattern")

    result = apply_event(
        case,
        Event(type="snoozed", at=date(2026, 9, 11), snoozed_until=date(2026, 10, 1)),
    )

    assert result.state == "snoozed"
    assert result.snoozed_until == date(2026, 10, 1)

def test_illegal_transition_is_refused():
    case = Case(case_id="EWS-001", state="open", case_type="bounce_pattern")

    with pytest.raises(InvalidTransition):
        apply_event(case, Event(type="snoozed", at=date(2026, 9, 11)))

def test_reopen_clears_outcome_and_closed_at():
    closed = Case(
        case_id="EWS-001",
        state="closed",
        case_type="bounce_pattern",
        outcome="recovered",
        closed_at=date(2026, 9, 11),
    )

    result = apply_event(closed, Event(type="reopened", at=date(2026, 9, 20)))

    assert result.state == "awaiting_review"
    assert result.outcome is None
    assert result.closed_at is None