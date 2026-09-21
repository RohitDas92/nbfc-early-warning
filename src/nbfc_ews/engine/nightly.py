from dataclasses import dataclass
from datetime import date

from nbfc_ews.db.repositories.cases import (
    append_event,
    create_case,
    escalate_case,
    open_cases,
)
from nbfc_ews.db.repositories.runs import claim_business_date
from nbfc_ews.engine.detect import detect, require_business_date
from nbfc_ews.engine.route import route_signals


class AlreadyProcessed(Exception):
    """This business date has already been run.  Running it again would
    duplicate every case event, so the run refuses - loudly, so that a
    scheduler repeating a finished date is noticed rather than hidden."""


@dataclass(frozen=True)
class NightlyRun:
    as_of: date
    accounts_scanned: int
    signals: int
    opened: int
    joined: int
    escalated: int

def run_nightly(conn, as_of: date) -> NightlyRun:
    """Detect, route and record one business date.  Once per date, ever.

    The caller owns the transaction.  Commit only after this returns, so the
    ledger claim and the case writes succeed or fail together."""
    require_business_date(as_of)
    if not claim_business_date(conn, as_of):
        raise AlreadyProcessed(f"{as_of} has already been processed")

    run = detect(conn, as_of)

    existing = open_cases(conn)
    cases_types = {acct: ct for acct, (_cid, ct) in existing.items()}
    case_ids = {acct : cid for acct, (cid,_ct) in existing.items()}

    actions = route_signals(run.signals, cases_types)

    opened = joined = escalated = 0

    for a in actions:
        if a.decision == "open":
            case_ids[a.account_id] = create_case(
                conn, a.account_id, a.case_type, a.signal, as_of
            )
            opened += 1

        elif a.decision == "escalate":
            escalate_case(conn, case_ids[a.account_id], a.case_type, a.signal, as_of)
            escalated += 1

        else:
            append_event(conn, case_ids[a.account_id],"signal_joined", a.signal, as_of)
            joined += 1

    return NightlyRun(
        as_of=as_of,
        accounts_scanned=run.accounts_scanned,
        signals=len(run.signals),
        opened=opened,
        joined=joined,
        escalated=escalated,
    )

