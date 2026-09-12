
from typing import Literal

RouteDecision = Literal["open", "join", "escalate"]

_SEVERITY: dict[str, int] = {
    "moratorium_ending": 1,
    "contactability_decay": 2,
    "payment_date_drift": 3,
    "part_payment": 4,
    "bounce_pattern": 5,
    "drift_with_bounce": 6,
    "bureau_deterioration": 7,
    "interest_not_serviced": 8,
    "tranche_not_requested": 9,
    "dpd_bucket_movement": 10,
    "adverse_event": 11,
}

def route(signal_type: str, open_case_type : str | None) -> RouteDecision:
    """Decide what to do with a signal, given the account's open case(if any)"""
    if open_case_type is None:
        return "open"

    if _SEVERITY[signal_type] > _SEVERITY[open_case_type]:
        return "escalate"

    return "join"

