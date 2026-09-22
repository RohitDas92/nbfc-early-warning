"""The case service: visibility, state changes, and every outcome recorded."""

from datetime import date

import pytest

from nbfc_ews.db.repositories.cases import create_case
from nbfc_ews.domain.principal import Principal
from nbfc_ews.domain.signals import Signal
from nbfc_ews.llm.fake import FakeChatModel, says
from nbfc_ews.services.case_service import (
    CaseNotFound,
    CaseNotInvestigable,
    begin_investigation,
    complete_investigation,
    get_case,
    list_cases,
)

AS_OF = date(2026, 7, 1)
ELSEWHERE = Principal(user_id="outsider", role="analyst", branch_ids=(-1,))


@pytest.fixture
def case(conn):
    """A fresh case on a real loan, and an analyst from that loan's branch."""
    account, branch = conn.execute(
        """
        select l.loan_account_no, l.branch_id
        from loan l
        where not exists (
            select 1 from ews_case c
            where c.account_id = l.loan_account_no and c.state <> 'closed'
        )
        limit 1
        """
    ).fetchone()
    conn.execute(
        "insert into nightly_run (as_of) values (%s) on conflict do nothing", [AS_OF]
    )
    signal = Signal(account_id=account, signal_type="bounce_pattern", detail="test")
    case_id = create_case(conn, account, "repayment", signal, AS_OF)
    analyst = Principal(user_id="analyst-1", role="analyst", branch_ids=(branch,))
    return case_id, analyst


def state_of(conn, case_id: str) -> str:
    return conn.execute(
        "select state from ews_case where case_id = %s", [case_id]
    ).fetchone()[0]


def test_an_analyst_sees_a_case_in_their_branch(conn, case) -> None:
    case_id, analyst = case

    listed = {c.case_id for c in list_cases(conn, analyst, limit=100_000)}

    assert case_id in listed


def test_a_case_in_another_branch_is_not_found(conn, case) -> None:
    case_id, _ = case

    assert case_id not in {c.case_id for c in list_cases(conn, ELSEWHERE)}
    with pytest.raises(CaseNotFound):
        get_case(conn, ELSEWHERE, case_id)


def test_beginning_moves_the_case_to_investigating(conn, case) -> None:
    case_id, analyst = case

    begin_investigation(conn, analyst, case_id, "fake")

    assert state_of(conn, case_id) == "investigating"
    detail = get_case(conn, analyst, case_id)
    assert detail.investigation is not None
    assert detail.investigation.status == "running"
    assert detail.events[-1].event_type == "investigation_started"
    assert detail.events[-1].actor == "analyst-1"


def test_a_second_begin_is_refused(conn, case) -> None:
    case_id, analyst = case
    begin_investigation(conn, analyst, case_id, "fake")

    with pytest.raises(CaseNotInvestigable):
        begin_investigation(conn, analyst, case_id, "fake")


def test_a_completed_run_is_stored_and_awaits_review(conn, case) -> None:
    case_id, analyst = case
    run = begin_investigation(conn, analyst, case_id, "fake")

    status = complete_investigation(
        conn, analyst, run, FakeChatModel([says("repayment is steady")])
    )

    assert status == "complete"
    assert state_of(conn, case_id) == "awaiting_review"
    stored = get_case(conn, analyst, case_id).investigation
    assert [f.text for f in stored.findings] == ["repayment is steady"]


def test_a_failed_run_is_recorded_and_escalated(conn, case) -> None:
    case_id, analyst = case
    run = begin_investigation(conn, analyst, case_id, "fake")

    # An empty script raises on the first model call - a stand-in for Azure failing.
    status = complete_investigation(conn, analyst, run, FakeChatModel([]))

    assert status == "failed"
    assert state_of(conn, case_id) == "escalated"
    stored = get_case(conn, analyst, case_id).investigation
    assert stored.status == "failed"
    assert "ScriptExhausted" in stored.error
