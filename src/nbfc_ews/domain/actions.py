from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

ActionType = Literal[
    "SOFT_CONTACT_BORROWER",
    "CONTACT_CO_APPLICANT",
    "MANDATE_REPAIR",
    "PAYMENT_DATE_CHANGE",
    "MORATORIUM_EXTENSION",
    "TENURE_EXTENSION",
    "HANDOVER_TO_COLLECTIONS",
    "FIELD_VISIT",
    "SETTLEMENT",
]

Authority = Literal["analyst", "manager", "head", "committee"]

WaiverType = Literal["interest", "principal"]

@dataclass(frozen=True)
class ActionRequest:
    """A proposed action, with whatever parameters that action needs."""

    action: ActionType
    waiver_type: WaiverType | None = None
    waiver_amount: Decimal | None = None

@dataclass(frozen=True)
class ActionFacts:
    """What the policy check needs to know about an account."""

    dpd: int
    in_moratorium: bool
    prior_actions: frozenset[str]

@dataclass(frozen= True)
class Precondition:
    """One row of action_policy, as the checker sees it."""

    action: ActionType
    min_dpd: int | None
    max_dpd: int | None
    requires_prior: tuple[ActionType, ...]
    forbidden_when: tuple[str, ...]
    authority: Authority | None
    source_clause: str | None

@dataclass(frozen = True)
class Denial:
    """Why an action was refused, and which rule refused it."""

    action: ActionType
    reason: str
    rule: str | None

