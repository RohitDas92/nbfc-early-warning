from dataclasses import dataclass
from datetime import date
from typing import Any

from psycopg.rows import dict_row

from nbfc_ews.domain.principal import Principal
from nbfc_ews.tools.base import ToolResult, failure, success

_LOAN_SQL = """
select id from loan
where loan_account_no = %(account_id)s
"""

_HISTORY_SQL = """
with bounds as (
    select
        l.id as loan_id,
        date_trunc('month', l.sanction_date)::date as first_month,
        (date_trunc('month', %(as_of)s::date) - interval '1 month')::date as last_month
    from loan l
    where l.loan_account_no = %(account_id)s
),
spine as (
    select
        generate_series(b.first_month, b.last_month, interval '1 month')::date as month,
        b.loan_id
    from bounds b
),
attempts as (
    select
        date_trunc('month', c.attempt_date)::date as month,
        count(*) as attempts,
        count(*) filter (where c.outcome = 'connected')      as connected,
        count(*) filter (where c.outcome = 'no_answer')      as no_answer,
        count(*) filter (where c.outcome = 'invalid_number') as invalid_number
    from contact_attempt c
    join bounds b on b.loan_id = c.loan_id
    group by 1
)
select
    s.month,
    coalesce(a.attempts, 0)       as attempts,
    coalesce(a.connected, 0)      as connected,
    coalesce(a.no_answer, 0)      as no_answer,
    coalesce(a.invalid_number, 0) as invalid_number
from spine s
left join attempts a on a.month = s.month
order by s.month desc
"""

@dataclass(frozen=True)
class GetContactHistory:
    name: str = "get_contact_history"
    description: str = (
        "Wheater this borrower could be reached, month by month. How many attepts"
        " were made, how many connected, how many went unanswered, and how many hit"
        " an invalid number. Months with no attempts appear with aeros, not as gaps."
        " A rise in invalid_number means the contact details are stale, which is a"
        " different problem from a borrower who is avoiding contact."
        " No phone number, email address or name is ever returned."
    )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "months": {
                    "type": ["integer", "null"],
                    "description": "How many months of contact history. Null for the default of 6.",
                },
            },
            "required": ["account_id", "months"],
            "additionalProperties": False,
        }

    def __call__(
            self,
            conn,
            principal:Principal,
            account_id: str,
            as_of: date,
            months: int = 6,
    ) -> ToolResult:
        """Contact attempts by month, most recent first."""
        if months< 1:
            return failure("months must be at least 1")

        loan = conn.execute(_LOAN_SQL, {"account_id": account_id}).fetchone()
        if loan is None:
            return failure(f"no account {account_id!r} available")

        cur = conn.cursor(row_factory=dict_row)
        rows = cur.execute(
            _HISTORY_SQL, {"account_id": account_id, "as_of": as_of}
        ).fetchall()

        data = [
            {**row, "month": row["month"].isoformat()}
            for row in rows[:months]
        ]

        return success(
            data=data,
            as_of=rows[0]["month"] if rows else None,
            omitted = max(0, len(rows) - months),
        )