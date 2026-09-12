from dataclasses import dataclass
from datetime import date
from typing import Literal

CaseState = Literal[
    "open",
    "investigating",
    "awaiting_review",
    "snoozed",
    "escalated",
    "closed",
]

CloseOutcome = Literal[
    "resolved_benign",
    "intervened",
    "escalated",
    "no_action_authorised",
]

EventType = Literal[
    "investigation_started",
    "investigation_completed",
    "investigation_failed",
    "signal_joined",
    "snoozed",
    "snoozed_expired",
    "escalation_required",
    "closed",
    "reopened"
]

@dataclass(frozen=True)
class Case:
    case_id: str
    state: CaseState
    case_type: str
    outcome: CloseOutcome | None = None
    snoozed_until: date | None = None
    closed_at: date | None = None

@dataclass(frozen=True)
class Event:
    type: EventType
    at: date
    outcome: CloseOutcome | None = None
    snoozed_until: date | None = None