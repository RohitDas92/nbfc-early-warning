"""Stored investigations: what the agents concluded, and from what.

Append-only.  There is deliberately no function that edits a finding or an
evidence row; a re-investigation is a new investigation.

Two transactions per run, owned by the caller:
  1. start_investigation, committed at once, so the screen can show "running"
  2. finish_investigation or fail_investigation, when the agents return
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # types only - the repository does not call into the agents
    from nbfc_ews.agents.context import Entry
    from nbfc_ews.agents.supervisor import Supervision

STALE_AFTER = timedelta(minutes=10)


class AlreadyRunning(Exception):
    """This case already has an investigation in progress."""


class NotRunning(Exception):
    """The investigation is no longer running - finished, failed or timed out."""


@dataclass(frozen=True)
class StoredFinding:
    agent: str
    text: str | None
    complete: bool
    turns: int
    tool_calls: int
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class StoredEvidence:
    agent: str
    tool: str
    arguments: dict[str, Any]
    ok: bool
    reason: str | None
    row_count: int
    rows: list[dict[str, Any]]
    recorded_at: datetime


@dataclass(frozen=True)
class StoredInvestigation:
    id: int
    case_id: str
    as_of: date
    model: str
    status: str
    requested_by: str
    started_at: datetime
    finished_at: datetime | None
    input_tokens: int | None
    output_tokens: int | None
    error: str | None
    findings: tuple[StoredFinding, ...]
    evidence: tuple[StoredEvidence, ...]


# --- writing ------------------------------------------------------------------

_EXPIRE_SQL = """
update investigation
set status = 'failed', error = 'timed out', finished_at = now()
where case_id = %(case_id)s
  and status = 'running'
  and started_at < now() - %(stale_after)s
"""

# on conflict, not try/except: a failed statement would abort the transaction.
_START_SQL = """
insert into investigation (case_id, as_of, model, requested_by)
values (%(case_id)s, %(as_of)s, %(model)s, %(requested_by)s)
on conflict (case_id) where status = 'running' do nothing
returning id
"""

_FINISH_SQL = """
update investigation
set status = %(status)s, finished_at = now(),
    input_tokens = %(input_tokens)s, output_tokens = %(output_tokens)s
where id = %(id)s and status = 'running'
"""

_FAIL_SQL = """
update investigation
set status = 'failed', finished_at = now(), error = %(error)s
where id = %(id)s and status = 'running'
"""

_FINDING_SQL = """
insert into finding (investigation_id, agent, text, complete, turns, tool_calls,
                     input_tokens, output_tokens)
values (%(investigation_id)s, %(agent)s, %(text)s, %(complete)s, %(turns)s,
        %(tool_calls)s, %(input_tokens)s, %(output_tokens)s)
"""

_EVIDENCE_SQL = """
insert into evidence (investigation_id, agent, tool, arguments, ok, reason,
                      row_count, rows, recorded_at)
values (%(investigation_id)s, %(agent)s, %(tool)s, %(arguments)s::jsonb, %(ok)s,
        %(reason)s, %(row_count)s, %(rows)s::jsonb, %(recorded_at)s)
"""


def start_investigation(
    conn,
    case_id: str,
    as_of: date,
    model: str,
    requested_by: str,
    stale_after: timedelta = STALE_AFTER,
) -> int:
    """Claim the case for one run.  Returns the investigation id.

    A run still 'running' after stale_after is taken to have crashed, and is
    failed first so it cannot lock the case forever.
    """
    conn.execute(_EXPIRE_SQL, {"case_id": case_id, "stale_after": stale_after})
    row = conn.execute(
        _START_SQL,
        {"case_id": case_id, "as_of": as_of, "model": model, "requested_by": requested_by},
    ).fetchone()
    if row is None:
        raise AlreadyRunning(f"{case_id} already has an investigation running")
    return int(row[0])


def finish_investigation(
    conn,
    investigation_id: int,
    supervision: "Supervision",
    entries: Sequence["Entry"],
) -> None:
    """Store every finding and every piece of evidence, and close the run."""
    closed = conn.execute(
        _FINISH_SQL,
        {
            "id": investigation_id,
            "status": "complete" if supervision.complete else "incomplete",
            "input_tokens": supervision.input_tokens,
            "output_tokens": supervision.output_tokens,
        },
    )
    if closed.rowcount != 1:
        raise NotRunning(f"investigation {investigation_id} is not running")

    for finding in supervision.findings:
        conn.execute(_FINDING_SQL, {
            "investigation_id": investigation_id,
            "agent": finding.agent,
            "text": finding.text,
            "complete": finding.complete,
            "turns": finding.turns,
            "tool_calls": finding.tool_calls,
            "input_tokens": finding.input_tokens,
            "output_tokens": finding.output_tokens,
        })

    for entry in entries:
        data = entry.result.data if entry.result.ok else []
        conn.execute(_EVIDENCE_SQL, {
            "investigation_id": investigation_id,
            "agent": entry.agent,
            "tool": entry.tool,
            "arguments": json.dumps(dict(entry.arguments), default=str),
            "ok": entry.result.ok,
            "reason": entry.result.reason,
            "row_count": len(data),
            "rows": json.dumps(data, default=str),
            "recorded_at": entry.recorded_at,
        })


def fail_investigation(conn, investigation_id: int, error: str) -> None:
    """Close the run as failed.  The error is kept; nothing else is written."""
    closed = conn.execute(_FAIL_SQL, {"id": investigation_id, "error": error[:2000]})
    if closed.rowcount != 1:
        raise NotRunning(f"investigation {investigation_id} is not running")


# --- reading ------------------------------------------------------------------

_LATEST_SQL = """
select id, case_id, as_of, model, status, requested_by, started_at, finished_at,
       input_tokens, output_tokens, error
from investigation
where case_id = %(case_id)s
order by id desc
limit 1
"""

_FINDINGS_SQL = """
select agent, text, complete, turns, tool_calls, input_tokens, output_tokens
from finding
where investigation_id = %(id)s
order by id
"""

_EVIDENCES_SQL = """
select agent, tool, arguments, ok, reason, row_count, rows, recorded_at
from evidence
where investigation_id = %(id)s
order by id
"""


def latest_investigation(conn, case_id: str) -> StoredInvestigation | None:
    """The most recent run on this case, with everything it found."""
    head = conn.execute(_LATEST_SQL, {"case_id": case_id}).fetchone()
    if head is None:
        return None

    (run_id, run_case, as_of, model, status, requested_by, started_at,
     finished_at, input_tokens, output_tokens, error) = head

    params = {"id": run_id}
    findings = tuple(
        StoredFinding(*row) for row in conn.execute(_FINDINGS_SQL, params).fetchall()
    )
    evidence = tuple(
        StoredEvidence(*row) for row in conn.execute(_EVIDENCES_SQL, params).fetchall()
    )
    return StoredInvestigation(
        id=run_id,
        case_id=run_case,
        as_of=as_of,
        model=model,
        status=status,
        requested_by=requested_by,
        started_at=started_at,
        finished_at=finished_at,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        error=error,
        findings=findings,
        evidence=evidence,
    )