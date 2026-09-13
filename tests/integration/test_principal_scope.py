import psycopg
import pytest

from nbfc_ews.db.engine import session
from nbfc_ews.domain.principal import Principal

pytestmark = pytest.mark.integration

ANALYST = Principal(user_id="rohit", role="analyst", branch_ids=(1, 2))
NOBODY = Principal(user_id="ghost", role="analyst", branch_ids=())
BATCH = Principal(user_id="nightly", role="batch", branch_ids="ALL")


def _loan_count(c):
    return c.execute("select count(*) from loan").fetchone()[0]


def test_batch_sees_the_whole_book(conn):
    with session(conn, BATCH) as c:
        assert _loan_count(c) == 10000


def test_analyst_sees_only_their_branches(conn):
    with session(conn, ANALYST) as c:
        total = _loan_count(c)
        off_scope = c.execute(
            "select count(*) from loan where branch_id not in (1, 2)"
        ).fetchone()[0]

    assert 0 < total < 10000
    assert off_scope == 0


def test_no_scope_sees_nothing(conn):
    with session(conn, NOBODY) as c:
        assert _loan_count(c) == 0


def test_app_rw_cannot_read_base_party_table(conn):
    with session(conn, ANALYST) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select * from party limit 1")