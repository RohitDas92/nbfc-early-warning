from nbfc_ews.domain.signals import AccountFacts

_FACTS_SQL = """
select
    l.id,
    l.loan_account_no,
    l.institution_id,
    cur.dpd,
    coalesce(prev.dpd, 0) as dpd_last_month,
    cur.is_in_moratorium,
    (l.moratorium_end_date - %(as_of)s::date) as days_to_moratorium_end
from loan l
join loan_month_state cur
  on cur.loan_id = l.id
 and cur.as_of_month = %(as_of)s
left join loan_month_state prev
  on prev.loan_id = l.id
 and prev.as_of_month = (%(as_of)s::date - interval '1 month')::date
"""

_BOUNCE_SQL = """
select
    p.loan_id,
    count(*) as bounces,
    max(p.retry_sequence) as max_retries
from presentation p
where p.status = 'bounce'
  and p.presentation_date >= (%(as_of)s::date - interval '3 months')
  and p.presentation_date <  (%(as_of)s::date + interval '1 month')
group by p.loan_id
"""

_PAYMENT_SQL = """
with monthly as (
    select
        p.loan_id,
        date_trunc('month', p.payment_date)::date as pay_month,
        min(extract(day from p.payment_date))::int as pay_day,
        sum(p.amount) as paid
    from payment p
    where p.payment_date >= (%(as_of)s::date - interval '2 months')
      and p.payment_date <  (%(as_of)s::date + interval '1 month')
    group by 1, 2
)
select
    m.loan_id,
    array_agg(m.pay_day order by m.pay_month) as pay_days,
    array_agg((m.paid / nullif(l.emi, 0))::float order by m.pay_month) as ratios
from monthly m
join loan l on l.id = m.loan_id
group by m.loan_id
"""

_BUREAU_SQL = """
with latest as (
    select distinct on (b.party_id)
        b.party_id, b.score, b.as_of_date, b.enquiries_last_60d
    from bureau_snapshot b
    where b.as_of_date <= %(as_of)s
      and b.as_of_date >  (%(as_of)s::date - interval '1 month')
    order by b.party_id, b.as_of_date desc
),
previous as (
    select distinct on (b.party_id)
        b.party_id, b.score
    from bureau_snapshot b
    join latest l on l.party_id = b.party_id
    where b.as_of_date < l.as_of_date
    order by b.party_id, b.as_of_date desc
)
select
    lp.loan_id,
    latest.score,
    previous.score as prev_score,
    latest.enquiries_last_60d
from latest
join loan_party lp
  on lp.party_id = latest.party_id
 and lp.is_primary_earner
left join previous on previous.party_id = latest.party_id
"""

_TRANCHE_SQL = """
select
    t.loan_id,
    max((%(as_of)s::date - t.expected_date))::int as days_past
from tranche t
where t.requested_date is null
  and t.expected_date < %(as_of)s
group by t.loan_id
"""

_CONTACT_SQL = """
select
    c.loan_id,
    count(*) as failed
from contact_attempt c
where c.outcome <> 'connected'
  and c.attempt_date >= (%(as_of)s::date - interval '60 days')
  and c.attempt_date <  (%(as_of)s::date + interval '1 month')
group by c.loan_id
"""

# NEW
_INTEREST_SQL = """
select
    lms.loan_id,
    count(*) as months_unserviced
from loan_month_state lms
join loan l on l.id = lms.loan_id
where lms.is_in_moratorium
  and l.interest_servicing_required
  and lms.overdue_interest > 0
  and lms.as_of_month >  (%(as_of)s::date - interval '3 months')
  and lms.as_of_month <= %(as_of)s
group by lms.loan_id
"""

_ADVERSE_SQL = """
select distinct on (a.loan_id)
    a.loan_id,
    a.event_type
from adverse_event a
where a.event_date <= %(as_of)s
  and a.event_date >  (%(as_of)s::date - interval '12 months')
order by a.loan_id, a.event_date desc
"""

def load_bounce_facts(conn, as_of) -> dict[int, tuple[int, int]]:
    """Bounces and worst retry count per loan over the last 3 months."""
    cur = conn.execute(_BOUNCE_SQL, {"as_of": as_of})
    return {
        loan_id: (bounces, max_retries or 0)
        for loan_id, bounces, max_retries in cur.fetchall()
    }


def load_payment_facts(conn, as_of) -> dict[int, tuple[tuple[int, ...], tuple[float, ...]]]:
    """Payment day-of-month and paid/EMI ratio for the last 3 months, per loan."""
    cur = conn.execute(_PAYMENT_SQL, {"as_of": as_of})
    return {
        loan_id: (tuple(pay_days), tuple(ratios))
        for loan_id, pay_days, ratios in cur.fetchall()
    }


def load_bureau_facts(conn, as_of) -> dict[int, tuple[int | None, int | None, int]]:
    """Latest and previous bureau score, plus recent enquiries, per loan."""
    cur = conn.execute(_BUREAU_SQL, {"as_of": as_of})
    return {
        loan_id: (score, prev_score, enquiries or 0)
        for loan_id, score, prev_score, enquiries in cur.fetchall()
    }


def load_tranche_facts(conn, as_of) -> dict[int, int]:
    """Days past the expected date for the oldest unrequested tranche, per loan."""
    cur = conn.execute(_TRANCHE_SQL, {"as_of": as_of})
    return {loan_id: days_past for loan_id, days_past in cur.fetchall()}


def load_contact_facts(conn, as_of) -> dict[int, int]:
    """Failed contact attempts in the last 60 days, per loan."""
    cur = conn.execute(_CONTACT_SQL, {"as_of": as_of})
    return {loan_id: failed for loan_id, failed in cur.fetchall()}

def load_interest_facts(conn, as_of) -> dict[int, int]:
    """Months of unserviced interest during moratorium, last 3 months, per loan."""
    cur = conn.execute(_INTEREST_SQL, {"as_of": as_of})
    return {loan_id: months for loan_id, months in cur.fetchall()}

def load_adverse_facts(conn, as_of) -> dict[int, str]:
    """The most recent reported adverse event per loan, within the last year."""
    cur = conn.execute(_ADVERSE_SQL, {"as_of": as_of})
    return {loan_id: event_type for loan_id, event_type in cur.fetchall()}

def load_account_facts(conn, as_of) -> list[AccountFacts]:
    """Read one month of portfolio state and build AccountFacts for every loan."""
    bounce_map = load_bounce_facts(conn, as_of)
    payment_map = load_payment_facts(conn, as_of)
    bureau_map = load_bureau_facts(conn, as_of)
    tranche_map = load_tranche_facts(conn, as_of)
    contact_map = load_contact_facts(conn, as_of)
    interest_map = load_interest_facts(conn, as_of)
    adverse_map = load_adverse_facts(conn, as_of)

    cur = conn.execute(_FACTS_SQL, {"as_of": as_of})

    facts = []

    for (
        loan_id, loan_account_no, institution_id, dpd, dpd_last_month,
        in_moratorium, days_to_moratorium_end,
    ) in cur.fetchall():
        bounces, retries = bounce_map.get(loan_id, (0, 0))
        pay_days, ratios = payment_map.get(loan_id, ((), ()))
        score, prev_score, enquiries = bureau_map.get(loan_id, (None, None, 0))
        days_past_tranche = tranche_map.get(loan_id)
        failed_contacts = contact_map.get(loan_id, 0)
        months_unserviced = interest_map.get(loan_id, 0)

        facts.append(
            AccountFacts(
                account_id=loan_account_no,
                dpd=dpd,
                dpd_last_month=dpd_last_month,
                institution_id=str(institution_id),
                bounces_last_3m=bounces,
                retries_on_last_bounce=retries,
                in_moratorium=in_moratorium,
                days_to_moratorium_end=days_to_moratorium_end,
                payment_days_last_3m=pay_days,
                paid_ratio_last_3m=ratios,
                bureau_score_now=score,
                bureau_score_prev=prev_score,
                new_enquiries_60d=enquiries,
                days_past_expected_tranche=days_past_tranche,
                failed_contacts_60d=failed_contacts,
                months_interest_unserviced=months_unserviced,
                adverse_event=adverse_map.get(loan_id),
            )
        )

    return facts