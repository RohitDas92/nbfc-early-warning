"""What the API asks for about cases - and nothing the API should know how to do.

Every read runs inside session(), so row-level security on `loan` decides which
cases a principal can see.  A case outside their branches is reported as not
found, never as forbidden: "forbidden" would confirm that it exists.

Each function is one transaction (conn.transaction()).  Call them on a clean
connection: inside an already-open transaction they become savepoints and
nothing is committed until the caller commits.
"""

import logging
from dataclasses import dataclass
from datetime import date

from nbfc_ews.agents.context import CaseContext
from nbfc_ews.agents.supervisor import supervise
from nbfc_ews.db.engine import session
from nbfc_ews.db.repositories.cases import append_event
from nbfc_ews.db.repositories.investigations import (
    StoredInvestigation,
    fail_investigation,
    finish_investigation,
    latest_investigation,
    start_investigation,
)
from nbfc_ews.domain.case_state import InvalidTransition, apply_event
from nbfc_ews.domain.models import Case, Event, EventType
from nbfc_ews.domain.principal import Principal
from nbfc_ews.llm.base import ChatModel

log = logging.getLogger(__name__)


class CaseNotFound(Exception):
    """No such case - or not one this principal may see.  Deliberately the same."""


class CaseNotInvestigable(Exception):
    """The case's state does not allow an investigation to start."""


@dataclass(frozen=True)
class CaseSummary:
    case_id: str
    account_id: str
    case_type: str
    state: str
    opened_at: date
    signals: tuple[str, ...]


@dataclass(frozen=True)
class CaseEvent:
    at: date
    event_type: str
    signal_type: str | None
    detail: str | None
    actor: str | None


@dataclass(frozen=True)
class CaseDetail:
    summary: CaseSummary
    events: tuple[CaseEvent, ...]
    investigation: StoredInvestigation | None


# The join to loan is what applies row-level security.  Never remove it.
_CASES_SQL = """
select c.case_id, c.account_id, c.case_type, c.state, c.opened_at,
       coalesce(
           array_agg(distinct e.signal_type) filter (where e.signal_type is not null),
           '{}'
       ) as signals
from ews_case c
join loan l on l.loan_account_no = c.account_id
left join case_event e on e.case_id = c.case_id
where (%(state)s::text is null or c.state = %(state)s)
  and (%(case_id)s::text is null or c.case_id = %(case_id)s)
group by c.case_id, c.account_id, c.case_type, c.state, c.opened_at
order by c.opened_at desc, c.case_id
limit %(limit)s
"""

_EVENTS_SQL = """
select at, event_type, signal_type, detail, actor
from case_event
where case_id = %(case_id)s
order by id
"""

_BUSINESS_DATE_SQL = "select max(as_of) from nightly_run"

# for update: two requests cannot move the same case at the same moment.
_LOCK_CASE_SQL = """
select state, case_type from ews_case where case_id = %(case_id)s for update
"""

_SET_STATE_SQL = "update ews_case set state = %(state)s where case_id = %(case_id)s"

_RUNNING_SQL = """
select case_id, as_of from investigation where id = %(id)s and status = 'running'
"""


def _summary(row) -> CaseSummary:
    case_id, account_id, case_type, state, opened_at, signals = row
    return CaseSummary(case_id, account_id, case_type, state, opened_at, tuple(signals))


def _visible_case(conn, case_id: str) -> CaseSummary:
    """The case, if this session may see it.  Must run inside session()."""
    row = conn.execute(
        _CASES_SQL, {"state": None, "case_id": case_id, "limit": 1}
    ).fetchone()
    if row is None:
        raise CaseNotFound(case_id)
    return _summary(row)


def _transition(conn, case_id: str, event_type: EventType, at: date, actor: str) -> None:
    """Move the case through the state machine and record why.  Never by hand."""
    row = conn.execute(_LOCK_CASE_SQL, {"case_id": case_id}).fetchone()
    if row is None:
        raise CaseNotFound(case_id)
    state, case_type = row
    moved = apply_event(
        Case(case_id=case_id, state=state, case_type=case_type),
        Event(type=event_type, at=at),
    )
    conn.execute(_SET_STATE_SQL, {"state": moved.state, "case_id": case_id})
    append_event(conn, case_id, event_type, None, at, actor=actor)


def list_cases(
    conn, principal: Principal, *, state: str | None = None, limit: int = 100
) -> list[CaseSummary]:
    """Cases this principal may see, newest first."""
    with conn.transaction(), session(conn, principal) as c:
        rows = c.execute(
            _CASES_SQL, {"state": state, "case_id": None, "limit": limit}
        ).fetchall()
    return [_summary(row) for row in rows]


def get_case(conn, principal: Principal, case_id: str) -> CaseDetail:
    """One case: its signals, its history, and its latest investigation."""
    with conn.transaction(), session(conn, principal) as c:
        summary = _visible_case(c, case_id)
        events = tuple(
            CaseEvent(*row) for row in c.execute(_EVENTS_SQL, {"case_id": case_id})
        )
        investigation = latest_investigation(c, case_id)
    return CaseDetail(summary=summary, events=events, investigation=investigation)


def begin_investigation(
    conn, principal: Principal, case_id: str, model_name: str
) -> int:
    """Claim the case and mark it investigating.  Fast - returns the run id.

    Committed before any agent runs, so a screen can show "running" at once.
    """
    with conn.transaction(), session(conn, principal) as c:
        _visible_case(c, case_id)
        (as_of,) = c.execute(_BUSINESS_DATE_SQL).fetchone()
        if as_of is None:
            raise CaseNotInvestigable("no business date has been processed yet")
        try:
            _transition(c, case_id, "investigation_started", as_of, principal.user_id)
        except InvalidTransition as exc:
            raise CaseNotInvestigable(f"{case_id}: {exc}") from exc
        return start_investigation(c, case_id, as_of, model_name, principal.user_id)


def complete_investigation(
    conn, principal: Principal, investigation_id: int, model: ChatModel
) -> str:
    """Run the agents and store what they found.  Slow - meant for the background.

    Returns the final status.  Never raises for an agent failure: this is the
    boundary of a background job, so every outcome is recorded, not thrown away.
    """
    with conn.transaction(), session(conn, principal) as c:
        row = c.execute(_RUNNING_SQL, {"id": investigation_id}).fetchone()
        if row is None:
            return "not_running"
        case_id, as_of = row
        summary = _visible_case(c, case_id)

    try:
        with conn.transaction(), session(conn, principal) as c:
            ctx = CaseContext(case_id=case_id, as_of=as_of)
            result = supervise(
                case_id=case_id,
                account_id=summary.account_id,
                signal_types=list(summary.signals),
                model=model,
                ctx=ctx,
                conn=c,
                principal=principal,
            )
            finish_investigation(c, investigation_id, result, ctx.entries())
            _transition(c, case_id, "investigation_completed", as_of, "system")
        return "complete" if result.complete else "incomplete"

    except Exception as exc:  # the job boundary: record every failure
        log.exception("investigation %s failed", investigation_id)
        with conn.transaction(), session(conn, principal) as c:
            fail_investigation(c, investigation_id, f"{type(exc).__name__}: {exc}")
            _transition(c, case_id, "investigation_failed", as_of, "system")
        return "failed"
