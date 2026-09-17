from datetime import date

import pytest

from nbfc_ews.agents.context import CaseContext
from nbfc_ews.agents.supervisor import plan, supervise
from nbfc_ews.db.engine import session
from nbfc_ews.domain.principal import Principal
from nbfc_ews.domain.routing import _SEVERITY
from nbfc_ews.llm.fake import FakeChatModel, calls_tool, says

AS_OF = date(2026, 6, 1)
ALL = Principal(user_id="t", role="analyst", branch_ids="ALL")


@pytest.fixture
def account(conn):
    row = conn.execute("select loan_account_no from loan limit 1").fetchone()
    assert row is not None
    return row[0]


@pytest.fixture
def ctx():
    return CaseContext(case_id="EWS-2026-06-00017", as_of=AS_OF)


# --- plan: no model, no database ---------------------------------------------

def test_every_signal_type_has_a_plan():
    for signal_type in _SEVERITY:
        assert plan([signal_type]), f"{signal_type} plans no investigator"


def test_an_unknown_signal_type_falls_back():
    assert plan(["something_invented_later"]) == ["repayment"]


def test_an_investigator_is_not_run_twice():
    assert plan(["bounce_pattern", "payment_date_drift", "part_payment"]) == ["repayment"]


def test_two_domains_get_two_investigators():
    assert plan(["dpd_bucket_movement"]) == ["repayment", "bureau"]


def test_the_order_is_stable():
    assert plan(["bureau_deterioration", "bounce_pattern"]) == ["bureau", "repayment"]


# --- supervise: needs the database -------------------------------------------

def test_one_investigator_runs_and_reports(conn, ctx, account):
    model = FakeChatModel([
        calls_tool("get_payment_behaviour", account_id=account, months=3),
        says("three months paid in full"),
    ])

    with session(conn, ALL) as c:
        result = supervise(
            case_id="EWS-2026-06-00017",
            account_id=account,
            signal_types=["bounce_pattern"],
            model=model,
            ctx=ctx,
            conn=c,
            principal=ALL,
        )

    assert result.agents_run == ("repayment",)
    assert result.complete is True
    assert len(result.findings) == 1
    assert result.input_tokens > 0


def test_two_investigators_share_one_context(conn, ctx, account):
    model = FakeChatModel([
        calls_tool("get_payment_behaviour", account_id=account),
        says("repayment is deteriorating"),
        calls_tool("get_bureau_history", account_id=account),
        says("co-applicant score falling"),
    ])

    with session(conn, ALL) as c:
        result = supervise(
            case_id="EWS-2026-06-00017",
            account_id=account,
            signal_types=["dpd_bucket_movement"],
            model=model,
            ctx=ctx,
            conn=c,
            principal=ALL,
        )

    assert result.agents_run == ("repayment", "bureau")
    assert len(result.findings) == 2

    agents = {entry.agent for entry in ctx.entries()}
    assert agents == {"repayment", "bureau"}


def test_an_incomplete_investigation_makes_the_whole_thing_incomplete(conn, ctx, account):
    model = FakeChatModel([
        calls_tool("get_payment_behaviour", call_id="c1", account_id=account, months=3),
        calls_tool("get_payment_behaviour", call_id="c2", account_id=account, months=6),
        calls_tool("get_payment_behaviour", call_id="c3", account_id=account, months=9),
        calls_tool("get_payment_behaviour", call_id="c4", account_id=account, months=12),
        calls_tool("get_payment_behaviour", call_id="c5", account_id=account, months=18),
        calls_tool("get_payment_behaviour", call_id="c6", account_id=account, months=24),
    ])

    with session(conn, ALL) as c:
        result = supervise(
            case_id="EWS-2026-06-00017",
            account_id=account,
            signal_types=["bounce_pattern"],
            model=model,
            ctx=ctx,
            conn=c,
            principal=ALL,
        )

    assert result.complete is False
    assert result.findings[0].text is None