"""Run the nightly batch:  python scripts/nightly.py 2026-06-01 [2026-07-01 ...]

All dates run in one transaction.  If any date fails - including one that was
already processed - nothing from this invocation is committed.
"""
import sys
from datetime import date

from nbfc_ews.db.engine import connect
from nbfc_ews.engine.nightly import AlreadyProcessed, run_nightly

months = sys.argv[1:] or ["2026-06-01"]

with connect() as conn:
    try:
        for m in months:
            result = run_nightly(conn, date.fromisoformat(m))
            print(result)
    except AlreadyProcessed as exc:
        conn.rollback()
        print(f"refused: {exc}. Nothing was written.", file=sys.stderr)
        sys.exit(1)
    conn.commit()
