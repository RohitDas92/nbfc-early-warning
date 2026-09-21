
"""Cases endpoints. Who is asking, call the service, translate its errors - noting else.

No SQL and no business rules live here. The response shapes below are the
API's contract: kept seperate from the service's own types, so that internals
can change without breaking whoever calls the API.
"""

from datetime import date, datetime
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from nbfc_ews.api.deps import (
    ConnectionScope,
    get_conn,
    get_connect,
    get_model,
    get_principal,
)
from nbfc_ews.db.repositories.investigations import AlreadyRunning
from nbfc_ews.domain.principal import Principal
from nbfc_ews.llm.base import ChatModel
from nbfc_ews.services.case_service import (
    CaseNotFound,
    CaseNotInvestigable,
    begin_investigation,
    complete_investigation,
    get_case,
    list_cases,
)

router = APIRouter(prefix="/cases", tags=["cases"])

Who = Annotated[Principal, Depends(get_principal)]
Conn = Annotated[psycopg.Connection, Depends(get_conn)]

# ------ response shape: the API's contract ---------------------------------------------------------

class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class CaseSummaryOut(_Out):
    case_id: str
    account_id: str
    case_type: str
    state: str
    opened_at: date
    signals: list[str]

class CaseEventOut(_Out):
    at: date
    event_type: str
    signal_type: str | None
    detail: str | None
    actor: str | None

class FindingOut(_Out):
    agent: str
    text: str | None
    complete: bool
    turns: int
    tool_calls: int
    input_tokens: int
    output_tokens: int

class EvidenceOut(_Out):
    agent: str
    tool: str
    arguments: dict[str, Any]
    ok: bool
    reason: str | None
    row_count: int
    rows: list[dict[str, Any]]
    recorded_at: datetime

class InvestigationOut(_Out):
    id: int
    as_of: date
    model: str
    status: str
    requested_by: str
    started_at: datetime
    finished_at: datetime | None
    input_tokens: int | None
    output_tokens: int | None
    error: str | None
    findings: list[FindingOut]
    evidence: list[EvidenceOut]

class CaseDetailOut(_Out):
    summary: CaseSummaryOut
    events: list[CaseEventOut]
    investigation: InvestigationOut | None

class InvestigationStarted(BaseModel):
    investigation_id: int


# --- endpoints --------------------------------------------------------------------------------------


@router.get("")
def list_cases_endpoint(
    principal: Who,
    conn: Conn,
    state: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[CaseSummaryOut]:

    """Cases the caler may see, newest first."""
    cases = list_cases(conn, principal, state=state, limit=limit)
    return [CaseSummaryOut.model_validate(case) for case in cases]


@router.get("/{case_id}")
def get_case_endpoint(case_id: str, principal: Who, conn: Conn) -> CaseDetailOut:
    """One case with its history and its latest investigation."""

    try:
        detail = get_case(conn, principal, case_id)
    except CaseNotFound:
        raise HTTPException(status_code=404, detail="case not found") from None
    return CaseDetailOut.model_validate(detail)

@router.post("/{case_id}/investigations", status_code=202)
def start_investigation_endpoint(
    case_id: str,
    background: BackgroundTasks,
    principal: Who,
    conn: Conn,
    open_connection: Annotated[ConnectionScope, Depends(get_connect)],
    model: Annotated[ChatModel, Depends(get_model)],
) -> InvestigationStarted:
    """Start an investigation. Answers at once; the agents run afterwards."""
    try:
        run_id = begin_investigation(conn, principal, case_id, model.name)
    except CaseNotFound:
        raise HTTPException(status_code=404, detail=" case not found") from None
    except (CaseNotInvestigable, AlreadyRunning) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

    background.add_task(_investigate, open_connection, principal, run_id, model)
    return InvestigationStarted(investigation_id=run_id)

def _investigate(
        open_connection: ConnectionScope, principal: Principal, run_id: int, model: ChatModel
) -> None:
    """Runs after the response is sent, om a connection of it own."""
    with open_connection() as conn:
        complete_investigation(conn, principal, run_id, model)



