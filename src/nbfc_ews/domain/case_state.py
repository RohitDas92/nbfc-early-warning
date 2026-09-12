from dataclasses import replace

from nbfc_ews.domain.models import Case, CaseState, Event, EventType


class InvalidTransition(Exception):
    """Raise when an event is not permitted from 
    current case's current state."""

_TRANSITIONS:dict[tuple[CaseState, EventType], CaseState] = {
    ("open", "investigation_started"): "investigating",
    ("investigating", "investigation_completed"): "awaiting_review",
    ("investigating", "investigation_failed"): "escalated",
    ("awaiting_review", "snoozed") : "snoozed",
    ("snoozed", "snoozed_expired"): "awaiting_review",
    ("investigating", "escalation_required"): "escalated",
    ("awaiting_review", "escalation_required"): "escalated",
    ("awaiting_review","closed"): "closed",
    ("escalated","closed") : "closed",
    ("closed","reopened"): "awaiting_review",
    ("open", "signal_joined"): "open",
    ("investigating", "signal_joined"): "investigating",
    ("awaiting_review", "signal_joined") : "awaiting_review",
    ("snoozed", "signal_joined"): "snoozed",         
}

def apply_event(case:Case, event:Event) -> Case:
    """Return a new Case when event is applied. 
    Raise error if move is illegal."""

    key = (case.state, event.type)

    if key not in _TRANSITIONS:
        raise InvalidTransition(
            f"{event.type} is not allowed for {case.state}"
        )

    new_state = _TRANSITIONS[key]

    if event.type == 'closed' and event.outcome is None:
        raise InvalidTransition("Closing a case required outcome")
    
    changes :dict = {"state":new_state}

    if event.type == "closed":
        changes["outcome"] = event.outcome
        changes["closed_at"] = event.at

    elif event.type == "snoozed":
        changes["outcome"] = event.outcome
        changes["snoozed_until"] = event.snoozed_until
    elif event.type == "reopened":
        changes["outcome"] = None
        changes["closed_at"] = None

    return replace(case,**changes)



