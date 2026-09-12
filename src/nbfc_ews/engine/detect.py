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


def detect(conn, as_of: date) -> DetectionRun:
    """Run every signal rule over the book for one month."""
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
