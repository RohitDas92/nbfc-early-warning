from collections import defaultdict
from datetime import date

import pytest

from nbfc_ews.db.engine import session
from nbfc_ews.domain.principal import Principal
from nbfc_ews.tools.bureau import GetBureauHistory

AS_OF = date(2026, 6, 1)

TOOL = GetBureauHistory()

ALL = Principal(user_id="t", role="analyst", branch_ids="ALL")
NOWHERE = Principal(user_id="t", role="analyst", branch_ids=(-1,))


@pytest.fixture
def account(conn):
    """An account whose borrower and co-applicant both have several pulls."""
    row = conn.execute("""
        select l.loan_account_no
        from loan l
        join loan_party lp on lp.loan_id = l.id
        join bureau_snapshot b on b.party_id = lp.party_id
        group by 1
        having count(distinct lp.role) = 2 and count(*) > 6
        limit 1
    """).fetchone()
    assert row is not None, "seed data has no loan with two parties and pulls"
    return row[0]


def _all_rows(conn, account):
    with session(conn, ALL) as c:
        return TOOL(c, ALL, account_id=account, as_of=AS_OF, limit=500)


def test_never_returns_a_pull_at_or_after_as_of(conn, account):
    r = _all_rows(conn, account)
    assert r.ok
    assert all(d["pull_date"] < AS_OF.isoformat() for d in r.data)


def test_role_and_pull_date_together_are_unique(conn, account):
    r = _all_rows(conn, account)
    keys = [(d["role"], d["pull_date"]) for d in r.data]
    assert len(keys) == len(set(keys))


def test_age_days_is_measured_from_as_of(conn, account):
    r = _all_rows(conn, account)
    for d in r.data:
        expected = (AS_OF - date.fromisoformat(d["pull_date"])).days
        assert d["age_days"] == expected


def test_delta_is_null_only_on_a_partys_first_pull(conn, account):
    r = _all_rows(conn, account)

    by_role = defaultdict(list)
    for d in r.data:
        by_role[d["role"]].append(d)

    assert len(by_role) == 2
    for rows in by_role.values():
        oldest, rest = rows[-1], rows[:-1]
        assert oldest["delta"] is None
        assert all(x["delta"] is not None for x in rest)


def test_limit_below_one_is_refused(conn, account):
    with session(conn, ALL) as c:
        r = TOOL(c, ALL, account_id=account, as_of=AS_OF, limit=0)

    assert r.ok is False
    assert r.data == []


def test_out_of_scope_is_indistinguishable_from_missing(conn, account):
    def shape(result, account_id):
        return (
            result.ok,
            result.data,
            result.omitted,
            result.as_of,
            result.reason.replace(account_id, "<id>"),
        )

    with session(conn, NOWHERE) as c:
        hidden = TOOL(c, NOWHERE, account_id=account, as_of=AS_OF)
        absent = TOOL(c, NOWHERE, account_id="EDU9999999", as_of=AS_OF)

    assert hidden.ok is False
    assert shape(hidden, account) == shape(absent, "EDU9999999")