from datetime import date

import pytest

from nbfc_ews.agents.context import CaseContext
from nbfc_ews.agents.investigate import investigate, specs_for
from nbfc_ews.db.engine import session
from nbfc_ews.domain.principal import Principal
from nbfc_ews.llm.fake import FakeChatModel, calls_tool, says

AS_OF = date(2026, 6, 1)
ALL = Principal(user_id="t", role="analyst", branch_ids="ALL")
QUESTION = "is repayment deteriorating?"


@pytest.fixture
def account(conn):
    row = conn.execute("select loan_account_no from loan limit 1").fetchone()
    assert row is not None
    return row[0]


@pytest.fixture
def ctx():
    return CaseContext(case_id="EWS-2026-06-00017", as_of=AS_OF)


def run(conn, ctx, script, max_turns=6):
    model = FakeChatModel(script)
    with session(conn, ALL) as c:
        return investigate(
            agent="repayment",
            question=QUESTION,
            model=model,
            ctx=ctx,
            conn=c,
            principal=ALL,
            max_turns=max_turns,
        )


def test_the_agent_sees_only_its_own_tools():
    names = {spec.name for spec in specs_for("repayment")}
    assert names == {"get_payment_behaviour", "find_similar_alerts", "get_contact_history"}
    assert specs_for("marketing") == []


def test_an_answer_with_no_tools_ends_the_loop(conn, ctx):
    finding = run(conn, ctx, [says("nothing to report")])

    assert finding.complete is True
    assert finding.text == "nothing to report"
    assert finding.turns == 1
    assert finding.tool_calls == 0


def test_a_tool_is_run_and_recorded(conn, ctx, account):
    finding = run(conn, ctx, [
        calls_tool("get_payment_behaviour", account_id=account, months=3),
        says("three months paid in full"),
    ])

    assert finding.complete is True
    assert finding.tool_calls == 1
    assert finding.turns == 2

    entries = ctx.entries()
    assert len(entries) == 1
    assert entries[0].agent == "repayment"
    assert entries[0].tool == "get_payment_behaviour"
    assert entries[0].result.ok


def test_the_same_call_twice_is_not_run_twice(conn, ctx, account):
    finding = run(conn, ctx, [
        calls_tool("get_payment_behaviour", call_id="c1", account_id=account, months=3),
        calls_tool("get_payment_behaviour", call_id="c2", account_id=account, months=3),
        says("done"),
    ])

    assert finding.turns == 3
    assert finding.tool_calls == 1          # the second was served from the context
    assert len(ctx.entries()) == 1


def test_a_forbidden_tool_does_not_stop_the_loop(conn, ctx, account):
    finding = run(conn, ctx, [
        calls_tool("get_bureau_history", account_id=account),        # not repayment's
        calls_tool("get_payment_behaviour", account_id=account),
        says("recovered and reported"),
    ])

    assert finding.complete is True
    assert finding.text == "recovered and reported"

    results = [e.result.ok for e in ctx.entries()]
    assert results == [False, True]


def test_the_loop_stops_at_max_turns(conn, ctx, account):
    finding = run(conn, ctx, [
        calls_tool("get_payment_behaviour", call_id="c1", account_id=account, months=3),
        calls_tool("get_payment_behaviour", call_id="c2", account_id=account, months=6),
    ], max_turns=2)

    assert finding.complete is False
    assert finding.text is None
    assert finding.turns == 2


def test_tokens_are_summed_over_every_call(conn, ctx, account):
    finding = run(conn, ctx, [
        calls_tool("get_payment_behaviour", account_id=account),
        says("done"),
    ])

    assert finding.input_tokens == 200      # 100 per call, two calls
    assert finding.output_tokens > 0