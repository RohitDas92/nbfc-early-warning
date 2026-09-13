from dataclasses import dataclass
from datetime import date

from psycopg.rows import dict_row

from nbfc_ews.domain.principal import Principal
from nbfc_ews.tools.base import ToolResult, failure, success

_LOAN_SQL = """
select emi from loan 
where loan_account_no = %(account_id)s
"""

_BUREAU_SQL = """
with bounds as (
    select
        l.id as loan_id,
        %(as_of)s::date as as_of,
        l.moratorium_end_date as moratorium_end_date
    from loan l
    where l.loan_account_no = %(account_id)s
),
pulls as (
    select
        lp.role,
        lp.is_primary_earner,
        b.as_of_date as pull_date,
        b.score,
        b.enquiries_last_60d,
        b.worst_dpd_elsewhere,
        b.active_accounts,
        b.total_monthly_obligations,
        lag(b.score) over (partition by lp.party_id order by b.as_of_date) as prev_score,
        lag(b.as_of_date) over (partition by lp.party_id order by b.as_of_date) as prev_date,
        bd.as_of as as_of,
        bd.moratorium_end_date as moratorium_end_date
    from bounds bd
    join loan_party lp on lp.loan_id = bd.loan_id
    join bureau_snapshot b on b.party_id = lp.party_id
    where b.as_of_date < bd.as_of
)
select
    role,
    is_primary_earner,
    pull_date,
    (as_of - pull_date) as age_days,
    score,
    score - prev_score as delta,
    (pull_date - prev_date) as gap_days,
    enquiries_last_60d,
    worst_dpd_elsewhere,
    active_accounts,
    total_monthly_obligations,
    case
        when as_of <= moratorium_end_date then role = 'co_applicant'
        else role = 'borrower'
    end as servicing
from pulls
order by pull_date desc, role
"""

@dataclass
class GetBureauHistory:
    name: str = "get_bureau_history"
    description: str = (
        "Bureau pulls for everyone on this loan - the borrower and the co-applicant -"
        " newest first, each with its age in days so a stale file is never read as"
        " current. delta compares a pull to that same person's previous pull, and"
        " gap_days says how far back that was; a fall of 40 over 90 days is not the"
        " same as over 700. serviving marks the party responsible for the repayment at"
        " this date - the co-applicant during moratorium, the borrower after."
        " Weight that party most heavily, but do not ignore the other."
        " Pulls are quarterly portfolio monitoring; this tool cannot request a new one"
    )

    def __call__(
            self,
            conn,
            principal: Principal,
            account_id: str,
            as_of: date,
            limit: int = 8,

    ) -> ToolResult:
        """Bureau pulls for both parties, newest first."""
        if limit < 1:
            return failure("limit must be at least 1")

        loan = conn.execute(_LOAN_SQL, {"account_id": account_id}).fetchone()
        if loan is None:
            return failure(f"no account {account_id!r} available")

        cur = conn.cursor(row_factory=dict_row)
        rows = cur.execute(
            _BUREAU_SQL, {"account_id": account_id, "as_of": as_of}
        ).fetchall()

        data = [
            {
                **r,
                "pull_date": r["pull_date"].isoformat(),
                "total_monthly_obligations": float(r["total_monthly_obligations"]),

            }
            for r in rows[:limit]
        ]

        return success(
            data = data,
            as_of=rows[0]["pull_date"] if rows else None,
            omitted= max(0, len(rows) - limit),
        )