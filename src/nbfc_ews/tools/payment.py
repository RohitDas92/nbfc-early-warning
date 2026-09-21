from dataclasses import dataclass
from datetime import date
from typing import Any

from nbfc_ews.domain.principal import Principal
from nbfc_ews.tools.base import ToolResult, failure, success

_LOAN_SQL = """
select emi from loan 
where loan_account_no = %(account_id)s
"""

_HISTORY_SQL = """
with bounds as (
    select
        l.id as loan_id,
        l.emi as emi,
        date_trunc('month', l.repayment_start_date)::date as emi_from,
        date_trunc('month', l.sanction_date)::date as first_month,
        (date_trunc('month', %(as_of)s::date) - interval '1 month')::date as last_month
    from loan l
    where l.loan_account_no = %(account_id)s
),
spine as (
    select
        generate_series(b.first_month, b.last_month, interval '1 month')::date as month,
        b.loan_id,
        b.emi,
        b.emi_from
    from bounds b
),
pay as (
    select
        date_trunc('month', p.payment_date)::date as month,
        sum(p.amount) as paid,
        min(extract(day from p.payment_date))::int as pay_day
    from payment p
    join bounds b on b.loan_id = p.loan_id
    group by 1
),
bounced as (
    select
        date_trunc('month', pr.presentation_date)::date as month,
        count(*) as bounces
    from presentation pr
    join bounds b on b.loan_id = pr.loan_id
    where pr.status = 'bounce'
    group by 1
)
select
    s.month,
    coalesce(pay.paid, 0) as paid,
    case
        when s.month < s.emi_from then null
        else round((coalesce(pay.paid, 0) / nullif(s.emi, 0))::numeric, 2)
    end as paid_ratio,
    pay.pay_day,
    coalesce(bounced.bounces, 0) as bounces
from spine s
left join pay on pay.month = s.month
left join bounced on bounced.month = s.month
order by s.month desc
"""

@dataclass(frozen=True)
class GetPaymentBehaviour:
    name: str = "get_payment_behaviour"
    description: str = (
    "One borrower's repayment history by month: amount paid, the proportion"
    " of the EMI it covered, the day it landed, and whether the mandate bounced."
    " Months with no payment appear with paid 0, not as gaps."
    " paid_ratio is null during the moratorium, when no EMI is due."
    " Use this to judge whether repayment is deteriorating."
    )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "months": {
                    "type": ["integer", "null"],
                    "description": "How many months of payment history. Null for the default of 12.",
                },
            },
            "required": ["account_id", "months"],
            "additionalProperties": False,
        }


    def __call__(
            self, 
            conn,
            principal: Principal,
            account_id: str,
            as_of: date,
            months: int = 12,
            ) -> ToolResult:
        """Repayment history by month, most recent first."""
        if months < 1:
            return failure("months must be at least 1")

        loan = conn.execute(_LOAN_SQL, {"account_id": account_id}).fetchone()
        if loan is None:
            return failure(f"no account {account_id!r} available")

        rows = conn.execute(_HISTORY_SQL, {"account_id": account_id, "as_of": as_of}).fetchall()

        data = [
            {
                "month": month.isoformat(),
                "paid": float(paid),
                "paid_ratio": float(ratio) if ratio is not None else None,
                "pay_day": pay_day,
                "bounces": bounces,
            } 
            for month, paid, ratio, pay_day, bounces in rows[:months]
        ]

        return success(
            data = data,
            as_of= rows[0][0] if rows else None,
            omitted=max(0, len(rows) - months),
        )
