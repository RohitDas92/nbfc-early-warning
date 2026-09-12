from datetime import date

import pytest

from nbfc_ews.engine.nightly import run_nightly

pytestmark = pytest.mark.integration


def test_nightly_is_idempotent(conn):
    conn.execute("delete from case_event")
    conn.execute("delete from ews_case")

    first = run_nightly(conn, date(2026, 6, 1))
    second = run_nightly(conn, date(2026, 6, 1))

    assert first.opened > 0
    assert second.opened == 0
    assert second.joined + second.escalated == second.signals