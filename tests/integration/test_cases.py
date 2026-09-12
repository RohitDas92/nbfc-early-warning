from datetime import date

import psycopg
import pytest

from nbfc_ews.db.repositories.cases import (
    append_event,
    create_case,
    escalate_case,
    open_case_types,
)
from nbfc_ews.domain.signals import Signal

pytestmark = pytest.mark.integration

AS_OF = date(2026, 6, 1)


def _sig(signal_type="bounce_pattern"):
    return Signal(account_id="TEST-A1", signal_type=signal_type, detail="two bounces")


def test_create_case_appears_in_open_cases(conn):
    case_id = create_case(conn, "TEST-A1", "bounce_pattern", _sig(), AS_OF)

    assert case_id.startswith("EWS-2026-06-")
    assert open_case_types(conn)["TEST-A1"] == "bounce_pattern"


def test_create_case_writes_an_event(conn):
    case_id = create_case(conn, "TEST-A1", "bounce_pattern", _sig(), AS_OF)

    cur = conn.execute("select event_type from case_event where case_id = %s", [case_id])
    assert [r[0] for r in cur.fetchall()] == ["case_opened"]


def test_join_appends_without_changing_the_case(conn):
    case_id = create_case(conn, "TEST-A1", "bounce_pattern", _sig(), AS_OF)

    append_event(conn, case_id, "signal_joined", _sig("moratorium_ending"), AS_OF)

    assert open_case_types(conn)["TEST-A1"] == "bounce_pattern"
    cur = conn.execute("select count(*) from case_event where case_id = %s", [case_id])
    assert cur.fetchone()[0] == 2


def test_escalate_changes_type_and_writes_event(conn):
    case_id = create_case(conn, "TEST-A1", "bounce_pattern", _sig(), AS_OF)

    escalate_case(conn, case_id, "adverse_event", _sig("adverse_event"), AS_OF)

    assert open_case_types(conn)["TEST-A1"] == "adverse_event"
    cur = conn.execute("select count(*) from case_event where case_id = %s", [case_id])
    assert cur.fetchone()[0] == 2


def test_second_open_case_for_same_account_is_refused(conn):
    create_case(conn, "TEST-A1", "bounce_pattern", _sig(), AS_OF)

    with pytest.raises(psycopg.errors.UniqueViolation):
        create_case(conn, "TEST-A1", "dpd_bucket_movement", _sig(), AS_OF)