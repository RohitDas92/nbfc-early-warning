_OPEN_CASES_SQL = """
select account_id, case_id, case_type
from ews_case
where state <> 'closed'
  and account_id is not null
"""

_APPEND_EVENT_SQL = """
insert into case_event (case_id, event_type, at, signal_type, detail, actor)
values (%(case_id)s, %(event_type)s, %(at)s, %(signal_type)s, %(detail)s, %(actor)s)
on conflict do nothing
"""

_NEXT_ID_SQL = "select nextval(pg_get_serial_sequence('ews_case','id'))"

_CREATE_CASE_SQL = """
insert into ews_case (id, case_id, account_id, case_type, opened_at)
values (%(id)s, %(case_id)s, %(account_id)s, %(case_type)s, %(as_of)s)
"""

_ESCALATE_SQL = """
update ews_case
set case_type = %(case_type)s,
    state = 'escalated'
where case_id = %(case_id)s
"""


def open_cases(conn) -> dict[str, tuple[str, str]]:
    """account_id -> (case_id, case_type) for every open account case."""
    cur = conn.execute(_OPEN_CASES_SQL)
    return {
        account_id: (case_id, case_type)
        for account_id, case_id, case_type in cur.fetchall()
    }


def open_case_types(conn) -> dict[str, str]:
    """account_id -> case_type. The shape route_signals expects."""
    return {
        account_id: case_type
        for account_id, (_case_id, case_type) in open_cases(conn).items()
    }


def append_event(conn, case_id: str, event_type: str, signal, at, actor="system") -> None:
    """Record something that happened to a case. Append-only.

    The same event for the same case on the same day is stored once; a
    repeat is silently dropped by the unique index ux_case_event_once."""
    conn.execute(_APPEND_EVENT_SQL, {
        "case_id": case_id,
        "event_type": event_type,
        "at": at,
        "signal_type": signal.signal_type if signal else None,
        "detail": signal.detail if signal else None,
        "actor": actor,
    })


def create_case(conn, account_id: str, case_type: str, signal, as_of) -> str:
    """Open a new case for an account. Returns the new case_id."""
    (seq,) = conn.execute(_NEXT_ID_SQL).fetchone()
    case_id = f"EWS-{as_of:%Y-%m}-{seq:05d}"

    conn.execute(_CREATE_CASE_SQL, {
        "id": seq,
        "case_id": case_id,
        "account_id": account_id,
        "case_type": case_type,
        "as_of": as_of,
    })

    append_event(conn, case_id, "case_opened", signal, as_of)
    return case_id


def escalate_case(conn, case_id: str, new_case_type: str, signal, at) -> None:
    """Re-type a case to a more severe concern and put it back in the queue."""
    conn.execute(_ESCALATE_SQL, {"case_id": case_id, "case_type": new_case_type})
    append_event(conn, case_id, "escalation_required", signal, at)