"""Nothing dated on or after the business date is visible to the detector.

Pinned to one account in the synthetic dataset whose two bounces both fall in
June 2026.  On 1 June they are the future; on 1 July they are the past.  If
the dataset is regenerated, re-pick an account with the same shape.
"""

from datetime import date

import pytest

from nbfc_ews.db.repositories.accounts import load_bounce_facts
from nbfc_ews.engine.detect import detect

ACCOUNT = "EDU0000417"


@pytest.fixture
def loan_id(conn) -> int:
    row = conn.execute(
        "select id from loan where loan_account_no = %s", [ACCOUNT]
    ).fetchone()
    assert row is not None, f"{ACCOUNT} is not in the dataset"
    return row[0]


def test_june_bounces_are_invisible_on_1_june(conn, loan_id) -> None:
    bounces, _ = load_bounce_facts(conn, date(2026, 6, 1)).get(loan_id, (0, 0))
    assert bounces == 0


def test_june_bounces_are_visible_on_1_july(conn, loan_id) -> None:
    bounces, _ = load_bounce_facts(conn, date(2026, 7, 1)).get(loan_id, (0, 0))
    assert bounces == 2


def test_the_business_date_must_be_the_first_of_a_month(conn) -> None:
    """Month-state rows exist per month.  A mid-month date has no clear meaning."""
    with pytest.raises(ValueError):
        detect(conn, date(2026, 6, 15))