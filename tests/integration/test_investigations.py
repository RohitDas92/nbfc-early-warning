"""Stored investigations: kept, never doubled, never stuck."""

from datetime import date, timedelta

import pytest

from nbfc_ews.agents.context import CaseContext
from nbfc_ews.agents.investigate import Finding
from nbfc_ews.agents.supervisor import Supervision
from nbfc_ews.db.repositories.cases import create_case
from nbfc_ews.db.repositories.investigations import (
    AlreadyRunning,
    NotRunning,
    fail_investigation,
    finish_investigation,
    latest_investigation,
    start_investigation,
)
from nbfc_ews.domain.signals import Signal
from nbfc_ews.tools.base import failure, success

AS_OF = date(2026, 7, 1)


@pytest.fixture
def case_id(conn) -> str:
    """A case of our own, so no test depends on which cases the dataset holds."""
    signal = Signal(account_id="TEST-ACC-1", signal_type="bounce_pattern", detail="test")
    return create_case(conn, "TEST-ACC-1", "repayment", signal, AS_OF)


def supervision(case_id: str) -> Supervision:
    findings = (
        Finding(agent="repayment", text="deteriorating", complete=True, turns=2,
                tool_calls=2, input_tokens=100, output_tokens=40),
        Finding(agent="bureau", text="stress elsewhere", complete=True, turns=2,
                tool_calls=1, input_tokens=80, output_tokens=30),
    )
    return Supervision(
        case_id=case_id, agents_run=("repayment", "bureau"), findings=findings,
        complete=True, input_tokens=180, output_tokens=70,
    )


def context(case_id: str) -> CaseContext:
    ctx = CaseContext(case_id=case_id, as_of=AS_OF)
    ctx.record("repayment", "get_payment_behaviour", {"account_id": "TEST-ACC-1", "months": 12},
               success([{"month": "2026-06-01", "bounces": 2}], AS_OF))
    ctx.record("repayment", "get_contact_history", {"account_id": "TEST-ACC-1", "months": 6},
               failure("no contact data"))
    ctx.record("bureau", "get_bureau_history", {"account_id": "TEST-ACC-1", "limit": 8},
               success([{"score": 703}, {"score": 753}], AS_OF))
    return ctx


def test_a_second_run_is_refused_while_one_is_running(conn, case_id) -> None:
    start_investigation(conn, case_id, AS_OF, "gpt-5-mini", "analyst-1")

    with pytest.raises(AlreadyRunning):
        start_investigation(conn, case_id, AS_OF, "gpt-5-mini", "analyst-1")


def test_finish_stores_every_finding_and_every_tool_call(conn, case_id) -> None:
    run = start_investigation(conn, case_id, AS_OF, "gpt-5-mini", "analyst-1")
    finish_investigation(conn, run, supervision(case_id), context(case_id).entries())

    stored = latest_investigation(conn, case_id)

    assert stored is not None
    assert stored.status == "complete"
    assert (stored.input_tokens, stored.output_tokens) == (180, 70)
    assert [f.agent for f in stored.findings] == ["repayment", "bureau"]
    assert [e.tool for e in stored.evidence] == [
        "get_payment_behaviour", "get_contact_history", "get_bureau_history",
    ]


def test_evidence_keeps_the_rows_and_the_failures(conn, case_id) -> None:
    run = start_investigation(conn, case_id, AS_OF, "gpt-5-mini", "analyst-1")
    finish_investigation(conn, run, supervision(case_id), context(case_id).entries())

    payment, contact, bureau = latest_investigation(conn, case_id).evidence

    assert payment.rows == [{"month": "2026-06-01", "bounces": 2}]
    assert payment.arguments == {"account_id": "TEST-ACC-1", "months": 12}
    assert (contact.ok, contact.reason, contact.row_count) == (False, "no contact data", 0)
    assert bureau.row_count == 2


def test_latest_is_the_newest_run_not_the_first(conn, case_id) -> None:
    first = start_investigation(conn, case_id, AS_OF, "gpt-5-mini", "analyst-1")
    fail_investigation(conn, first, "boom")
    second = start_investigation(conn, case_id, AS_OF, "gpt-5-mini", "analyst-2")

    assert latest_investigation(conn, case_id).id == second


def test_a_stuck_run_is_failed_when_a_new_one_starts(conn, case_id) -> None:
    stuck = start_investigation(conn, case_id, AS_OF, "gpt-5-mini", "analyst-1")
    conn.execute(
        "update investigation set started_at = now() - interval '11 minutes' where id = %s",
        [stuck],
    )

    fresh = start_investigation(conn, case_id, AS_OF, "gpt-5-mini", "analyst-1",
                                stale_after=timedelta(minutes=10))

    status, error = conn.execute(
        "select status, error from investigation where id = %s", [stuck]
    ).fetchone()
    assert (status, error) == ("failed", "timed out")
    assert fresh != stuck


def test_a_failed_run_keeps_its_error(conn, case_id) -> None:
    run = start_investigation(conn, case_id, AS_OF, "gpt-5-mini", "analyst-1")
    fail_investigation(conn, run, "Azure returned 429")

    stored = latest_investigation(conn, case_id)
    assert (stored.status, stored.error) == ("failed", "Azure returned 429")
    assert stored.findings == ()


def test_a_finished_run_cannot_be_finished_again(conn, case_id) -> None:
    run = start_investigation(conn, case_id, AS_OF, "gpt-5-mini", "analyst-1")
    finish_investigation(conn, run, supervision(case_id), [])

    with pytest.raises(NotRunning):
        finish_investigation(conn, run, supervision(case_id), [])
