"""Run the nightly batch:  python scripts/nightly.py 2026-06-01"""
import sys
from datetime import date

from nbfc_ews.db.engine import connect
from nbfc_ews.engine.nightly import run_nightly

months = sys.argv[1:] or ["2026-06-01"]

with connect() as conn:
    for m in months:
        result = run_nightly(conn, date.fromisoformat(m))
        print(result)
    conn.commit()