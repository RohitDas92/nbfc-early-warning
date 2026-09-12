import pytest

from nbfc_ews.db.engine import connect


@pytest.fixture
def conn():
    """A connection whose work is always rolled back, so tests leave no trace."""
    c = connect()
    try:
        yield c
    finally:
        c.rollback()
        c.close()