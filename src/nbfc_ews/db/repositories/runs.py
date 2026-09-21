"""The nightly run ledger: which business dates have been processed."""

from datetime import date

# on conflict do nothing, not try/except: in Postgres a failed statement
# aborts the whole transaction, so catching a unique violation here would
# leave the connection unusable.  "returning" tells us whether we got the row.
_CLAIM_SQL = """
insert into nightly_run (as_of)
values (%(as_of)s)
on conflict (as_of) do nothing
returning as_of
"""


def claim_business_date(conn, as_of: date) -> bool:
    """Record that this date is being processed.  False if it already was.

    Must run inside the same transaction as the work itself, so that a failed
    run releases its claim when it rolls back.
    """
    return conn.execute(_CLAIM_SQL, {"as_of": as_of}).fetchone() is not None
