from dataclasses import dataclass
from datetime import date

from nbfc_ews.db.repositories.cases import (
    append_event,
    create_case,
    escalate_case,
    open_cases,
)
from nbfc_ews.engine.detect import detect
from nbfc_ews.engine.route import route_signals


@dataclass(frozen=True)
class NightlyRun:
    as_of: date
    accounts_scanned: int
    signals: int
    opened: int
    joined: int
    escalated: int

def run_nightly(conn, as_of:date) -> NightlyRun:
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

