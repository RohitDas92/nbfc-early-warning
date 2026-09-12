import psycopg

from nbfc_ews.config import DATABASE_URL


def connect() -> psycopg.Connection:
    """Open a connection for EWS Database."""
    return psycopg.connect(DATABASE_URL)


