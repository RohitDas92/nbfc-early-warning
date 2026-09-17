from datetime import date
from itertools import pairwise

import pytest

from nbfc_ews.db.engine import session
from nbfc_ews.domain.principal import Principal
from nbfc_ews.tools.contact import GetContactHistory

AS_OF = date(2026, 6, 1)

TOOL = GetContactHistory()

ALL = Principal(user_id="t", role="analyst", branch_ids="ALL")
NOWHERE = Principal(user_id="t", role="analyst", branch_ids=(-1,))

EXPECTED_KEYS = {
    "month",
    "attempts",
    "connected",
    "no_answer",
    "invalid_number",
}


@pytest.fixture
def account(conn):
    """The account with the most contact attempts, so there is something to see."""
    row = conn.execute("""
        select l.loan_account_no
        from contact_attempt c
        join loan l on l.id = c.loan_id
        group by 1
        order by count(*) desc
        limit 1
    """).fetchone()
    assert row is not None, "seed data has no contact attempts"
    return row[0]


@pytest.fixture
def result(conn, account):
    with session(conn, ALL) as c:
        return TOOL(c, ALL, account_id=account, as_of=AS_OF, months=240)


def test_never_returns_a_month_at_or_after_as_of(result):
    assert result.ok
    assert result.data
    assert all(row["month"] < AS_OF.isoformat() for row in result.data)


def test_no_gaps_in_the_month_series(result):
    months = [date.fromisoformat(row["month"]) for row in result.data]
    for newer, older in pairwise(months):
        gap = (newer.year - older.year) * 12 + (newer.month - older.month)
        assert gap == 1, f"gap between {older} and {newer}"


def test_the_outcomes_add_up_to_the_attempts(result):
    for row in result.data:
        total = row["connected"] + row["no_answer"] + row["invalid_number"]
        assert total == row["attempts"], row


def test_a_month_with_no_attempts_is_a_row_of_zeros(result):
    quiet = [r for r in result.data if r["attempts"] == 0]
    assert quiet, "this account was contacted every single month — pick another"
    for row in quiet:
        assert row["connected"] == 0
        assert row["no_answer"] == 0
        assert row["invalid_number"] == 0


def test_no_contact_details_are_returned(result):
    for row in result.data:
        assert set(row) == EXPECTED_KEYS


def test_omitted_reports_what_was_cut(conn, account):
    with session(conn, ALL) as c:
        few = TOOL(c, ALL, account_id=account, as_of=AS_OF, months=6)
        many = TOOL(c, ALL, account_id=account, as_of=AS_OF, months=240)

    assert few.omitted == len(many.data) - 6
    assert many.omitted == 0


def test_months_below_one_is_refused(conn, account):
    with session(conn, ALL) as c:
        r = TOOL(c, ALL, account_id=account, as_of=AS_OF, months=0)

    assert r.ok is False
    assert r.data == []


def test_out_of_scope_is_indistinguishable_from_missing(conn, account):
    def shape(res, acct):
        return (res.ok, res.data, res.omitted, res.as_of,
                res.reason.replace(acct, "<id>"))

    with session(conn, NOWHERE) as c:
        hidden = TOOL(c, NOWHERE, account_id=account, as_of=AS_OF)
        absent = TOOL(c, NOWHERE, account_id="EDU9999999", as_of=AS_OF)

    assert hidden.ok is False
    assert shape(hidden, account) == shape(absent, "EDU9999999")