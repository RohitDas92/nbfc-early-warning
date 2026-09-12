from dataclasses import dataclass

from nbfc_ews.domain.routing import RouteDecision, route
from nbfc_ews.domain.signals import Signal


@dataclass(frozen=True)
class CaseAction:
    account_id: str
    decision: RouteDecision
    case_type: str
    signal: Signal

def route_signals(
        signals:list[Signal],
        open_case_types: dict[str, str] | None = None,
) -> list[CaseAction]:
    """Route a batch of signals into open/join/escalate decisions."""

    current: dict[str, str]  = dict(open_case_types or {})

    actions = []

    for s in signals:
        decision = route(s.signal_type, current.get(s.account_id))

        if decision in ("open", "escalate"):
            current[s.account_id] = s.signal_type

        actions.append(
            CaseAction(
                account_id=s.account_id,
                decision=decision,
                case_type=current[s.account_id],
                signal=s,
            )
        )
    return actions