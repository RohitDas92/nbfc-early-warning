import psycopg
from contextlib import contextmanager

from nbfc_ews.config import DATABASE_URL
from nbfc_ews.domain.principal import Principal

_DB_ROLE: dict[str, str] = {
    "analyst": "app_rw",
    "manager": "app_rw",
    "batch": "app_rw",
    "admin": "pii_rw",
}


def connect() -> psycopg.Connection:
    """Open a connection for EWS Database."""
    return psycopg.connect(DATABASE_URL)

@contextmanager
def session(conn, principal:Principal):
    """Run queries as this principal, scoped to their branches, for this transaction."""
    scope = (
        "ALL"
        if principal.branch_ids == "ALL"
        else ",".join(str(b) for b in principal.branch_ids)
    )
    role = _DB_ROLE[principal.role]

    conn.execute("select set_config('app.branch_ids', %s, true)", [scope])
    conn.execute(f"set local role {role}")

    try:
        yield conn
    finally:
        try:
            conn.execute("reset role")
        except psycopg.Error:
            # The transaction is already aborted, so RESET is refused.
            # SET LOCAL ROLE reverts at transaction end anyway, so nothing leaks.
            pass



