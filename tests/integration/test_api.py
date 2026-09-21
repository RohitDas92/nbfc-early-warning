"""The HTTP layer: identity, status codes, and the background investigation.

The connection and the model are swapped for the test connection and a fake,
so nothing is committed and nothing costs money.
"""

from contextlib import nullcontext
from datetime import date

import pytest
from fastapi.testclient import TestClient

from nbfc_ews.api.deps import get_conn, get_connect, get_model
from nbfc_ews.api.main import app
from nbfc_ews.db.repositories.cases import create_case
from nbfc_ews.domain.signals import Signal
from nbfc_ews.llm.fake import FakeChatModel, says

AS_OF = date(2026, 7, 1)
OUTSIDER = {"X-User-Id": "outsider", "X-Role": "analyst", "X-Branches": "-1"}


@pytest.fixture
def client(conn):
    def shared_conn():
        yield conn  # never closed here - the conn fixture rolls it back

    app.dependency_overrides[get_conn] = shared_conn
    app.dependency_overrides[get_connect] = lambda: (lambda: nullcontext(conn))
    app.dependency_overrides[get_model] = lambda: FakeChatModel([says("repayment is steady")])
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def case(conn) -> tuple[str, dict[str, str]]:
    """A fresh case on a real loan, and headers for an analyst of its branch."""
    account, branch = conn.execute(
        """
        select l.loan_account_no, l.branch_id
        from loan l
        where not exists (
            select 1 from ews_case c
            where c.account_id = l.loan_account_no and c.state <> 'closed'
        )
        limit 1
        """
    ).fetchone()
    conn.execute(
        "insert into nightly_run (as_of) values (%s) on conflict do nothing", [AS_OF]
    )
    signal = Signal(account_id=account, signal_type="bounce_pattern", detail="test")
    case_id = create_case(conn, account, "repayment", signal, AS_OF)
    headers = {"X-User-Id": "analyst-1", "X-Role": "analyst", "X-Branches": str(branch)}
    return case_id, headers


def test_health_needs_no_identity(client) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_no_identity_is_401(client) -> None:
    assert client.get("/cases").status_code == 401


def test_admin_cannot_be_claimed_through_a_header(client) -> None:
    headers = {"X-User-Id": "x", "X-Role": "admin", "X-Branches": "ALL"}
    assert client.get("/cases", headers=headers).status_code == 401


def test_a_case_in_another_branch_is_404_not_403(client, case) -> None:
    case_id, _ = case
    assert client.get(f"/cases/{case_id}", headers=OUTSIDER).status_code == 404


def test_investigate_answers_202_then_the_findings_are_stored(client, case) -> None:
    case_id, headers = case

    started = client.post(f"/cases/{case_id}/investigations", headers=headers)

    assert started.status_code == 202
    # TestClient runs background tasks before post() returns, so it is done.
    detail = client.get(f"/cases/{case_id}", headers=headers).json()
    assert detail["summary"]["state"] == "awaiting_review"
    assert detail["investigation"]["status"] == "complete"
    assert detail["investigation"]["findings"][0]["text"] == "repayment is steady"


def test_a_second_investigate_is_409(client, case) -> None:
    case_id, headers = case
    client.post(f"/cases/{case_id}/investigations", headers=headers)

    again = client.post(f"/cases/{case_id}/investigations", headers=headers)

    assert again.status_code == 409