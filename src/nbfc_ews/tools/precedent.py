from dataclasses import dataclass
from datetime import date
from typing import Any

from psycopg.rows import dict_row

from nbfc_ews.domain.principal import Principal
from nbfc_ews.tools.base import ToolResult, failure, success

_LOAN_SQL = """
select emi from loan 
where loan_account_no = %(account_id)s
"""

_STATE_SQL = """
select s.bucket, s.is_in_moratorium
from loan l
join loan_month_state s on s.loan_id = l.id
where l.loan_account_no = %(account_id)s
  and s.as_of_month = date_trunc('month', %(as_of)s::date)
"""

_PRECEDENT_SQL = """
with acted as (
    select
        i.action_type,
        date_trunc('month', i.actioned_at)::date as at_month,
        i.loan_id,
        s.dpd as dpd_then
    from intervention i
    join loan_month_state s
      on s.loan_id = i.loan_id
     and s.as_of_month = date_trunc('month', i.actioned_at)::date
    where s.bucket = %(bucket)s
      and s.is_in_moratorium = %(in_moratorium)s
      and date_trunc('month', i.actioned_at)::date
            + make_interval(months => %(window_months)s)
          <= date_trunc('month', %(as_of)s::date)
),
outcome as (
    select
        a.action_type,
        a.at_month,
        case
            when later.dpd = 0           then 'cured'
            when later.dpd <= a.dpd_then then 'stable'
            else 'worsened'
        end as result
    from acted a
    join loan_month_state later
      on later.loan_id = a.loan_id
     and later.as_of_month =
         (a.at_month + make_interval(months => %(window_months)s))::date
)
select
    action_type,
    count(*) as n,
    round(count(*) filter (where result = 'cured')::numeric    / count(*), 2) as cured,
    round(count(*) filter (where result = 'stable')::numeric   / count(*), 2) as stable,
    round(count(*) filter (where result = 'worsened')::numeric / count(*), 2) as worsened,
    max(at_month) as latest_precedent_month
from outcome
group by 1
order by n desc
"""

@dataclass(frozen=True)
class FindSimilarAlerts:
    name: str = "find_similar_alerts"
    description: str = (
        "What was done to accounts in the same delinquency bucket and moratorium"
        " state as this one, and how those account stood a few months later:"
        " cured (DPD back to zero). stable (no worse), or worsened."
        " Every row carries n - treat a rate over a handful of cases as weak."
        " chosen by analysts, not assigned at random, so a harsher action such as"
        " handover to collections correlates with a worst account to begin with."
        " An empty results means no comparable precedent, not that nothing works."
    )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "window_months": {"type": "integer", "default": 3},
            },
            "required": ["account_id"],
        }
    
    def __call__(
            self,
            conn,
            principal: Principal,
            account_id: str,
            as_of: date,
            window_months: int = 3,
    )->ToolResult:
        """Historical actions mix and outcomes for accounts in a comparable state."""
        if window_months < 1:
            return failure ("window_months must be at least 1")

        state = conn.execute(
            _STATE_SQL, {"account_id": account_id, "as_of": as_of}
        ).fetchone()
        if state is None:
            return failure(f"no account {account_id!r} available")

        bucket, in_moratorium = state

        cur = conn.cursor(row_factory=dict_row)
        rows = cur.execute(_PRECEDENT_SQL,
                           {"bucket": bucket,
                            "in_moratorium": in_moratorium,
                            "as_of": as_of,
                            "window_months": window_months
                            },).fetchall()

        data = [
            {
                **r,
                "cured": float(r["cured"]),
                "stable": float(r["stable"]),
                "worsened": float(r["worsened"]),
                "matched_bucket":bucket,
                "matched_in_moratorium": in_moratorium,
                "window_months": window_months,
                "latest_precedent_month": r["latest_precedent_month"].isoformat(),
            }
            for r in rows
        ]

        return success(data=data, as_of=as_of, omitted=0)

    