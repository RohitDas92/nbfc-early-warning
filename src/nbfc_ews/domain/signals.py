from collections import Counter
from dataclasses import dataclass

from nbfc_ews.domain.classification import bucket_of


@dataclass(frozen= True)
class AccountFacts:
    account_id: str
    dpd: int
    dpd_last_month: int
    bounces_last_3m: int = 0
    retries_on_last_bounce: int = 0
    days_to_moratorium_end: int | None = None
    payment_days_last_3m: tuple[int, ...] = ()
    paid_ratio_last_3m: tuple[float, ...] = ()
    in_moratorium: bool = False
    months_interest_unserviced: int = 0
    bureau_score_now: int | None = None
    bureau_score_prev: int | None = None
    new_enquiries_60d: int = 0
    days_past_expected_tranche: int | None = None
    failed_contacts_60d: int = 0
    adverse_event: str | None = None
    institution_id: str | None = None

@dataclass(frozen=True)
class Signal:
    account_id: str
    signal_type: str
    detail: str

@dataclass(frozen=True)
class CohortSignal:
    institution_id: str
    signal_type: str
    detail: str

def check_dpd_bucket_movement(facts:AccountFacts) -> Signal| None:
    """Fires when an account moves into a worse delinquency"""

    before = bucket_of(facts.dpd_last_month)
    now = bucket_of(facts.dpd)

    if now != before:

        return Signal(
            account_id = facts.account_id,
            signal_type="dpd_bucket_movement",
            detail = f"DPD Moved {facts.dpd_last_month} to {facts.dpd},  ({before} to {now}).  "
        )
    return None

def check_bounce_pattern(facts: AccountFacts) -> Signal | None:
    """Fires on repeat bounces, 
    or one bounce that needed multiple retries."""

    repeat = facts.bounces_last_3m >= 2
    struggling = facts.bounces_last_3m >= 1 and facts.retries_on_last_bounce >= 2

    if repeat or struggling:
        return Signal(
            account_id = facts.account_id,
            signal_type="bounce_pattern",
            detail = f"{facts.bounces_last_3m} bounces in 3 months, {facts.retries_on_last_bounce} retries on last"
         )
    return None

def check_moratorium_ending(facts:AccountFacts) -> Signal | None:
    """Fires 75 days before a moratorium ends, so outreach can start."""
    if facts.days_to_moratorium_end is None:
        return None
    if 0<= facts.days_to_moratorium_end <= 75:
        return Signal(
            account_id = facts.account_id,
            signal_type="moratorium_ending",
            detail = f"moratorium ends in {facts.days_to_moratorium_end} days",
        )

def check_payment_date_drift(facts: AccountFacts) -> Signal | None:
    """Fires when payment land progressively later each month."""
    days = facts.payment_days_last_3m
    if len(days) < 3:
        return None

    drifting = days[0] < days[1] < days[2]
    material = days[2] - days[0] >= 7

    if drifting and material:
        return Signal(
            account_id = facts.account_id,
            signal_type="payment_date_drift",
            detail = f"payment day moved {days[0]} to {days[2]} over 3 months",
        )

def check_part_payment(facts:AccountFacts) -> Signal | None:
    """Fires when the borrower services the loan but cannot cover the full EMI"""
    ratios = facts.paid_ratio_last_3m

    if facts.in_moratorium:
        return None

    if len(ratios) < 2:
        return None

    last_two  = ratios[-2:]
    short_paid = all(r< 0.95 for r in last_two)
    paying_someting = all(r>0 for r in last_two)

    if short_paid and paying_someting:
        return Signal(
            account_id = facts.account_id,
            signal_type="part_payment",
            detail = f"{last_two[0]: .0%} then {last_two[1]: .0%} of EMI due"
        )

    return None

def check_drift_with_bounce(facts: AccountFacts) -> Signal | None:
    """More Severe: Payments drifting later AND a bounce in the same window."""
    if check_payment_date_drift(facts) is None:
        return None

    if facts.bounces_last_3m >= 1:
        return Signal(
            account_id = facts.account_id,
            signal_type="drift_with_bounce",
            detail = f"payment drift plus {facts.bounces_last_3m} bounces in last 3 months"
        )
    return None

def check_interest_not_serviced(facts: AccountFacts) -> Signal | None:
    """Fires when interest goes unpaid during Moratorium."""
    if not facts.in_moratorium:
        return None

    if facts.months_interest_unserviced >= 2:
        return Signal(
            account_id = facts.account_id,
            signal_type="interest_not_serviced",
            detail = f"interest unserviced for {facts.months_interest_unserviced} months in moratorium",
        )
    return None

def check_bureau_deterioration(facts: AccountFacts) -> Signal | None:
    """Fires on a sharp bureau score drop or a burt of new credit enquiries."""
    score_dropped = False
    if facts.bureau_score_now is not None and facts.bureau_score_prev is not None:
        score_dropped = facts.bureau_score_prev - facts.bureau_score_now >= 40

    enquiry_burst = facts.new_enquiries_60d >= 3

    if score_dropped or enquiry_burst:
        return  Signal(
            account_id = facts.account_id,
            signal_type="bureau_deterioration",
            detail = f"score {facts.bureau_score_prev} to {facts.bureau_score_now}, {facts.new_enquiries_60d} enquires in 60 days"
        )
    return None

def check_tranche_not_requested(facts: AccountFacts) -> Signal | None:
    """Fires when a disbursment due for a new semester was never requested."""

    if facts.days_past_expected_tranche is None:
        return None

    if facts.days_past_expected_tranche >= 30:
        return Signal(
            account_id = facts.account_id,
            signal_type="tranche_not_requested",
            detail = f"{facts.days_past_expected_tranche} days past expected tranche request"
        )
    return None

def check_contactability_decay(facts: AccountFacts) -> Signal | None:
    """Fires when borrowers can no longer be reached."""

    if facts.failed_contacts_60d >= 2:
        return Signal(
            account_id = facts.account_id,
            signal_type="contactability_decay",
            detail = f"{facts.failed_contacts_60d} failed to contact in 60 days"
        )
    return None
    
def check_adverse_event(facts: AccountFacts) -> Signal | None:
    """Fires on a reported event that changes the borrower's situation."""
    if facts.adverse_event is None:
        return None

    return Signal(
        account_id=facts.account_id,
        signal_type="adverse_event",
        detail=f"reported event: {facts.adverse_event}",
    )

def check_institution_cohort(flagged: list[AccountFacts], all_accounts: list[AccountFacts]) -> list[CohortSignal]:
    """Firest when several accounts from one institution are flagged together."""
    flagged_counts = Counter(
         f.institution_id for f in flagged if f.institution_id is not None)

    total_counts = Counter(
        f.institution_id for f in all_accounts if f.institution_id is not None)

    base_rate = len(flagged) / len(all_accounts) if all_accounts else 0

    out = []
    for institution_id, n in flagged_counts.items():
        total = total_counts[institution_id]
        rate = n / total

        if n >= 5 and rate >= 2 * base_rate:
            out.append(
                CohortSignal(
                    institution_id=institution_id,
                    signal_type="institution_event",
                    detail=f"{n} of {total} flagged ({rate:.0%} vs portfolio {base_rate:.0%})",
                )
            )
    return out

_RULES = [
    check_dpd_bucket_movement,
    check_bounce_pattern,
    check_moratorium_ending,
    check_payment_date_drift,
    check_part_payment,
    check_drift_with_bounce,
    check_interest_not_serviced,
    check_bureau_deterioration,
    check_tranche_not_requested,
    check_contactability_decay,
    check_adverse_event,
]

def evaluate(facts:AccountFacts) -> list[Signal]:
    """Run every rule over one account and return the signals that fired."""
    fired = []
    for rule in _RULES:
        signal = rule(facts)
        if signal is not None:
            fired.append(signal)
    return fired