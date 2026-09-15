from datetime import date

import pytest

from nbfc_ews.agents.dispatch import dispatch
from nbfc_ews.db.engine import session
from nbfc_ews.domain.principal import Principal
from nbfc_ews.llm.base import ToolCall

AS_OF = date(2026, 6, 1)
ALL = Principal(user_id="t", role="analyst", branch_ids="ALL")


@pytest.fixture
def account(conn):
    row = conn.execute("select loan_account_no from loan limit 1").fetchone()
    assert row is not None
    return row[0]


def call(name, **arguments):
    return ToolCall(id="c1", name=name, arguments=arguments)


def test_a_permitted_tool_runs(conn, account):
    with session(conn, ALL) as c:
        result = dispatch(
            call("get_payment_behaviour", account_id=account, months=3),
            "repayment", c, ALL, AS_OF,
        )

    assert result.ok
    assert result.data


def test_another_agents_tool_is_refused(conn, account):
    with session(conn, ALL) as c:
        result = dispatch(
            call("get_bureau_history", account_id=account),
            "repayment", c, ALL, AS_OF,
        )

    assert result.ok is False
    assert result.data == []


def test_a_forbidden_tool_and_a_nonexistent_one_look_the_same(conn, account):
    with session(conn, ALL) as c:
        forbidden = dispatch(
            call("get_bureau_history", account_id=account),
            "repayment", c, ALL, AS_OF,
        )
        imaginary = dispatch(
            call("get_bureau_history_v2", account_id=account),
            "repayment", c, ALL, AS_OF,
        )

    assert forbidden.reason.replace("get_bureau_history", "X") == \
           imaginary.reason.replace("get_bureau_history_v2", "X")


def test_the_model_cannot_supply_the_principal(conn, account):
    with session(conn, ALL) as c:
        result = dispatch(
            ToolCall(id="c1", name="get_payment_behaviour",
                     arguments={"account_id": account, "principal": "admin"}),
            "repayment", c, ALL, AS_OF,
        )

    assert result.ok is False
    assert "principal" in result.reason


def test_the_model_cannot_choose_as_of(conn, account):
    with session(conn, ALL) as c:
        result = dispatch(
            ToolCall(id="c1", name="get_payment_behaviour",
                     arguments={"account_id": account, "as_of": "2099-01-01"}),
            "repayment", c, ALL, AS_OF,
        )

    assert result.ok is False


def test_a_bad_argument_returns_rather_than_raises(conn, account):
    with session(conn, ALL) as c:
        result = dispatch(
            call("get_payment_behaviour", acount_id=account),
            "repayment", c, ALL, AS_OF,
        )

    assert result.ok is False
    assert "get_payment_behaviour" in result.reason


def test_an_unknown_agent_gets_nothing(conn, account):
    with session(conn, ALL) as c:
        result = dispatch(
            call("get_payment_behaviour", account_id=account),
            "marketing", c, ALL, AS_OF,
        )

    assert result.ok is False