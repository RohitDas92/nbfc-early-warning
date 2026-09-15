from datetime import date, datetime

from nbfc_ews.agents.context import CaseContext
from nbfc_ews.tools.base import failure, success

AS_OF = date(2026, 6, 1)


def ctx():
    return CaseContext(case_id="EWS-2026-06-00017", as_of=AS_OF)


def payments(n=3):
    return success(data=[{"month": "2026-05-01"}] * n, as_of=AS_OF)


def test_one_agent_reads_what_another_recorded():
    c = ctx()
    c.record("repayment", "get_payment_behaviour", {"account_id": "X"}, payments())

    found = c.read("get_payment_behaviour", account_id="X")

    assert found is not None
    assert found.data


def test_a_different_question_is_not_served_from_the_cache():
    c = ctx()
    c.record("repayment", "get_payment_behaviour",
             {"account_id": "X", "months": 3}, payments())

    assert c.read("get_payment_behaviour", account_id="X", months=3) is not None
    assert c.read("get_payment_behaviour", account_id="X", months=24) is None


def test_argument_order_does_not_matter():
    c = ctx()
    c.record("repayment", "get_payment_behaviour",
             {"months": 3, "account_id": "X"}, payments())

    assert c.read("get_payment_behaviour", account_id="X", months=3) is not None


def test_a_failure_is_logged_but_not_served():
    c = ctx()
    c.record("repayment", "get_payment_behaviour", {"account_id": "X"},
             failure("no account 'X' available"))

    assert c.read("get_payment_behaviour", account_id="X") is None
    assert len(c.entries()) == 1
    assert c.entries()[0].result.ok is False


def test_every_entry_is_attributed_and_timestamped():
    c = ctx()
    c.record("bureau", "get_bureau_history", {"account_id": "X"}, payments())

    entry = c.entries()[0]
    assert entry.agent == "bureau"
    assert entry.tool == "get_bureau_history"
    assert isinstance(entry.recorded_at, datetime)
    assert entry.recorded_at.tzinfo is not None


def test_recording_twice_keeps_both_and_serves_the_first():
    c = ctx()
    c.record("repayment", "get_payment_behaviour", {"account_id": "X"}, payments(n=3))
    c.record("bureau", "get_payment_behaviour", {"account_id": "X"}, payments(n=9))

    assert len(c.entries()) == 2
    assert len(c.read("get_payment_behaviour", account_id="X").data) == 3


def test_entries_cannot_be_appended_to_from_outside():
    c = ctx()
    c.record("repayment", "get_payment_behaviour", {"account_id": "X"}, payments())

    snapshot = c.entries()
    assert isinstance(snapshot, tuple)
    assert len(c.entries()) == 1


def test_as_of_is_carried_not_derived():
    c = ctx()
    assert c.as_of == AS_OF