from datetime import date

import pytest

from nbfc_ews.db.engine import session
from nbfc_ews.domain.principal import Principal
from nbfc_ews.tools.precedent import FindSimilarAlerts

AS_OF = date(2026, 6, 1)
WINDOW = 3

TOOL = FindSimilarAlerts()

ALL = Principal(user_id="t", role="analyst", branch_ids="ALL")
NOWHERE = Principal(user_id="t", role="analyst", branch_ids=(-1,))

EXPECTED_KEYS = {
    "action_type",
    "n",
    "cured",
    "stable",
    "worsened",
    "latest_precedent_month",
    "matched_bucket",
    "matched_in_moratorium",
    "window_months",
}


def _add_months(d: date, months: int) -> date:
    """First of the month, `months` later. date has no month arithmetic of its own."""
    m = d.month - 1 + months
    return date(d.year + m // 12, m % 12 + 1, 1)


@pytest.fixture
def subject(conn):
    """A delinquent account as last known on AS_OF - the month that has just
    ended, never AS_OF's own month, which has not happened yet."""
    row = conn.execute(
        """
        select l.loan_account_no, s.bucket, s.is_in_moratorium
        from loan l
        join loan_month_state s on s.loan_id = l.id
        where s.as_of_month = %(month)s
          and s.bucket = '31-60'
        limit 1
        """,
        {"month": _add_months(AS_OF, -1)},
    ).fetchone()
    assert row is not None, "seed data has no 31-60 account in the month before AS_OF"
    return row


@pytest.fixture
def result(conn, subject):
    account_id, _bucket, _mor = subject
    with session(conn, ALL) as c:
        return TOOL(c, ALL, account_id=account_id, as_of=AS_OF, window_months=WINDOW)


def test_no_outcome_window_reaches_as_of(result):
    assert result.ok
    assert result.data, "no precedent found — the rest of the suite proves nothing"

    for row in result.data:
        started = date.fromisoformat(row["latest_precedent_month"])
        # Strictly before: an outcome in AS_OF's own month is not yet observable.
        assert _add_months(started, WINDOW) < AS_OF


def test_every_row_carries_a_sample_size(result):
    for row in result.data:
        assert row["n"] >= 1


def test_the_three_rates_sum_to_one(result):
    for row in result.data:
        total = row["cured"] + row["stable"] + row["worsened"]
        assert abs(total - 1.0) < 0.02, row


def test_precedents_match_the_subjects_state(result, subject):
    _account_id, bucket, in_moratorium = subject
    for row in result.data:
        assert row["matched_bucket"] == bucket
        assert row["matched_in_moratorium"] == in_moratorium


def test_no_account_level_field_is_returned(result):
    for row in result.data:
        assert set(row) == EXPECTED_KEYS


def test_window_below_one_is_refused(conn, subject):
    account_id, _bucket, _mor = subject
    with session(conn, ALL) as c:
        r = TOOL(c, ALL, account_id=account_id, as_of=AS_OF, window_months=0)

    assert r.ok is False
    assert r.data == []


def test_out_of_scope_is_indistinguishable_from_missing(conn, subject):
    account_id, _bucket, _mor = subject

    def shape(res, acct):
        return (res.ok, res.data, res.omitted, res.as_of,
                res.reason.replace(acct, "<id>"))

    with session(conn, NOWHERE) as c:
        hidden = TOOL(c, NOWHERE, account_id=account_id, as_of=AS_OF)
        absent = TOOL(c, NOWHERE, account_id="EDU9999999", as_of=AS_OF)

    assert hidden.ok is False
    assert shape(hidden, account_id) == shape(absent, "EDU9999999")