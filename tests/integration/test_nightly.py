"""A business date is processed once.  Re-running it is refused, and writes nothing."""

from datetime import date

import pytest

from nbfc_ews.db.repositories.cases import append_event
from nbfc_ews.domain.signals import Signal
from nbfc_ews.engine.nightly import AlreadyProcessed, run_nightly

pytestmark = pytest.mark.integration

JUNE = date(2026, 6, 1)
JULY = date(2026, 7, 1)


@pytest.fixture
def clean(conn):
    """Empty case tables and ledger.  The conn fixture rolls all of this back."""
    conn.execute("delete from case_event")
    conn.execute("delete from ews_case")
    conn.execute("delete from nightly_run")
    return conn


def counts(conn) -> tuple[int, int]:
    cases = conn.execute("select count(*) from ews_case").fetchone()[0]
    events = conn.execute("select count(*) from case_event").fetchone()[0]
    return cases, events


def test_a_business_date_opens_cases(clean) -> None:
    assert run_nightly(clean, JUNE).opened > 0


def test_running_the_same_date_again_is_refused(clean) -> None:
    run_nightly(clean, JUNE)

    with pytest.raises(AlreadyProcessed):
        run_nightly(clean, JUNE)


def test_a_refused_rerun_writes_nothing(clean) -> None:
    run_nightly(clean, JUNE)
    before = counts(clean)

    with pytest.raises(AlreadyProcessed):
        run_nightly(clean, JUNE)

    assert counts(clean) == before


def test_the_next_business_date_still_runs(clean) -> None:
    run_nightly(clean, JUNE)
    july = run_nightly(clean, JULY)

    assert july.signals > 0


def test_a_mid_month_date_is_refused_before_anything_is_claimed(clean) -> None:
    with pytest.raises(ValueError):
        run_nightly(clean, date(2026, 6, 15))

    claimed = clean.execute("select count(*) from nightly_run").fetchone()[0]
    assert claimed == 0


def test_the_same_event_cannot_be_stored_twice(clean) -> None:
    """Defence in depth: holds even for code paths outside the nightly job."""
    run_nightly(clean, JUNE)
    (case_id,) = clean.execute("select case_id from ews_case limit 1").fetchone()
    signal = Signal(account_id="any", signal_type="bounce_pattern", detail="test")

    append_event(clean, case_id, "manual_note", signal, JUNE)
    append_event(clean, case_id, "manual_note", signal, JUNE)

    stored = clean.execute(
        "select count(*) from case_event where case_id = %s and event_type = 'manual_note'",
        [case_id],
    ).fetchone()[0]
    assert stored == 1
