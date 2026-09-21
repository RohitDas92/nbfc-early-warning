"""Delete every system-generated case and re-detect from scratch.

    python scripts/rebuild_cases.py --yes 2026-06-01 2026-07-01

Use after a detector rule changes, so stored cases reflect the current rules.
One transaction: either every date is rebuilt, or nothing changes at all.

Refuses if any case event was written by a person.  System cases can be
regenerated; an analyst's work cannot.
"""

import sys
from datetime import date

from nbfc_ews.db.engine import connect
from nbfc_ews.engine.nightly import run_nightly

_HUMAN_EVENTS = "select count(*) from case_event where actor <> 'system'"


def main() -> None:
    args = sys.argv[1:]
    if "--yes" not in args:
        raise SystemExit(
            "this deletes every case. Re-run with --yes to confirm:\n"
            "  python scripts/rebuild_cases.py --yes 2026-06-01 2026-07-01"
        )
    dates = sorted(date.fromisoformat(a) for a in args if a != "--yes")
    if not dates:
        raise SystemExit("give at least one business date, e.g. 2026-06-01")

    with connect() as conn:
        (human,) = conn.execute(_HUMAN_EVENTS).fetchone()
        if human:
            raise SystemExit(
                f"refused: {human} case events were written by people. "
                "Rebuilding would destroy their work."
            )

        before_cases = conn.execute("select count(*) from ews_case").fetchone()[0]
        conn.execute("delete from case_event")
        conn.execute("delete from ews_case")
        conn.execute("delete from nightly_run")
        # Case ids are built from this sequence; restart it so a rebuild is
        # reproducible - same data, same rules, same case ids.
        conn.execute("select setval(pg_get_serial_sequence('ews_case', 'id'), 1, false)")
        print(f"deleted {before_cases} cases")

        for as_of in dates:
            print(run_nightly(conn, as_of))

        conn.commit()
        print("committed")


if __name__ == "__main__":
    main()
