from dataclasses import dataclass
from datetime import date

from nbfc_ews.db.repositories.accounts import load_account_facts
from nbfc_ews.domain.signals import (
    CohortSignal,
    Signal,
    check_institution_cohort,
    evaluate,
)


@dataclass(frozen=True)
class DetectionRun:
    as_of: date
    accounts_scanned: int
    signals: list[Signal]
    cohort_signals: list[CohortSignal]


def require_business_date(as_of: date) -> None:
    """Month-state rows exist once per month, so a mid-month business date
    has no clear meaning.  Refuse it rather than guess."""
    if as_of.day != 1:
        raise ValueError(f"business date must be the first of a month, got {as_of}")


def detect(conn, as_of: date) -> DetectionRun:
    """Run every signal rule over the book for one month."""
    require_business_date(as_of)
    facts = load_account_facts(conn, as_of)

    signals: list[Signal] = []
    flagged = []

    for f in facts:
        fired = evaluate(f)
        if fired:
            signals.extend(fired)
            flagged.append(f)

    return DetectionRun(
        as_of=as_of,
        accounts_scanned=len(facts),
        signals=signals,
        cohort_signals=check_institution_cohort(flagged, facts),
    )
