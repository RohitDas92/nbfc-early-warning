"""Interactive session bootstrap.

    python -i scripts/shell.py

Everything you normally import by hand is already here, and `conn` is open.
"""
from collections import Counter
from datetime import date

from nbfc_ews.db.engine import connect
from nbfc_ews.db.repositories.accounts import load_account_facts
from nbfc_ews.domain.signals import evaluate
from nbfc_ews.engine.detect import detect

conn = connect()

print("ready:  conn  load_account_facts  evaluate  detect  Counter  date")
print("try:    run = detect(conn, date(2026, 6, 1))")
