"""Run detection over the book for one or more months.

    python scripts/detect_run.py
    python scripts/detect_run.py 2026-04-01 2026-05-01 2026-06-01
"""
import sys
from collections import Counter
from datetime import date

from nbfc_ews.db.engine import connect
from nbfc_ews.engine.detect import detect

months = sys.argv[1:] or ["2026-06-01"]

with connect() as conn:
    for m in months:
        run = detect(conn, date.fromisoformat(m))
        print(f"\n=== {m}   accounts={run.accounts_scanned:,}   "
              f"signals={len(run.signals):,}   cohort={len(run.cohort_signals)}")

        counts = Counter(s.signal_type for s in run.signals)
        for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"    {name:26s} {n:>6,}")

        for c in run.cohort_signals:
            print(f"    COHORT {c.institution_id}: {c.detail}")
