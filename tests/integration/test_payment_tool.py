from datetime import date
from itertools import pairwise

import pytest

from nbfc_ews.db.engine import session
from nbfc_ews.domain.principal import Principal
from nbfc_ews.tools.payment import GetPaymentBehaviour

AS_OF = date(2026, 6, 1)

TOOL = GetPaymentBehaviour()

ALL = Principal(user_id="t", role="analyst", branch_ids="ALL")
NOWHERE = Principal(user_id="t", role="analyst", branch_ids=(-1,))


@pytest.fixture
def account(conn):
    """An account with a long payment history, so slicing has something to slice."""
    row = conn.execute("""
        select l.loan_account_no
        from loan l
        join payment p on p.loan_id = l.id
        group by 1
        having count(*) > 20
        limit 1
    """).fetchone()
    assert row is not None, "seed data has no account with >20 payments"
    return row[0]


def test_newest_first_and_capped(conn, account):
    with session(conn, ALL) as c:
        r = TOOL(c, ALL, account_id=account, as_of=AS_OF, months=3)

    assert r.ok
    months = [d["month"] for d in r.data]
    assert len(months) == 3
    assert months == sorted(months, reverse=True)


def test_never_returns_a_month_at_or_after_as_of(conn, account):
    with session(conn, ALL) as c:
        r = TOOL(c, ALL, account_id=account, as_of=AS_OF, months=240)

    assert all(d["month"] < AS_OF.isoformat() for d in r.data)


def test_no_gaps_in_the_month_series(conn, account):
    with session(conn, ALL) as c:
        r = TOOL(c, ALL, account_id=account, as_of=AS_OF, months=240)

    months = [date.fromisoformat(d["month"]) for d in r.data]
    for newer, older in pairwise(months):
        gap = (newer.year - older.year) * 12 + (newer.month - older.month)
        assert gap == 1, f"gap between {older} and {newer}"


def test_omitted_reports_what_was_cut(conn, account):
    with session(conn, ALL) as c:
        few = TOOL(c, ALL, account_id=account, as_of=AS_OF, months=3)
        many = TOOL(c, ALL, account_id=account, as_of=AS_OF, months=240)

    assert few.omitted == len(many.data) - 3
    assert many.omitted == 0


def test_months_below_one_is_refused(conn, account):
    with session(conn, ALL) as c:
        r = TOOL(c, ALL, account_id=account, as_of=AS_OF, months=0)

    assert r.ok is False
    assert r.data == []


def _shape(result, account_id):
    """The response with the caller's own id blanked out."""
    return (
        result.ok,
        result.data,
        result.omitted,
        result.as_of,
        result.reason.replace(account_id, "<id>"),
    )


def test_out_of_scope_is_indistinguishable_from_missing(conn, account):
    with session(conn, NOWHERE) as c:
        hidden = TOOL(c, NOWHERE, account_id=account, as_of=AS_OF)
        absent = TOOL(c, NOWHERE, account_id="EDU9999999", as_of=AS_OF)

    assert hidden.ok is False
    assert _shape(hidden, account) == _shape(absent, "EDU9999999")