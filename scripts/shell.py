"""Interactive session bootstrap.

    python -i scripts/shell.py

Everything you normally import by hand is already here, and `conn` is open.
"""

from nbfc_ews.db.engine import connect

conn = connect()

print("ready:  conn  load_account_facts  evaluate  detect  Counter  date")
print("try:    run = detect(conn, date(2026, 6, 1))")
