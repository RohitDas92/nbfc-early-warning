from nbfc_ews.domain.signals import AccountFacts, check_dpd_bucket_movement, evaluate


def test_dpd_crossing_into_30_fires():
    facts = AccountFacts(account_id="A1", dpd=34, dpd_last_month=12)

    result = check_dpd_bucket_movement(facts)

    assert result is not None
    assert result.signal_type == "dpd_bucket_movement"

def test_already_above_30_does_not_fire():
    facts = AccountFacts(account_id="A1", dpd=50, dpd_last_month=45)

    assert check_dpd_bucket_movement(facts) is None


def test_just_under_threshold_does_not_fire():
    facts = AccountFacts(account_id="A1", dpd=29, dpd_last_month=12)

    assert check_dpd_bucket_movement(facts) is None

def test_thirty_to_thirtyone_fires():
    facts = AccountFacts(account_id="A1", dpd=31, dpd_last_month=30)

    assert check_dpd_bucket_movement(facts) is not None


def test_twentynine_to_thirty_does_not_fire():
    facts = AccountFacts(account_id="A1", dpd=30, dpd_last_month=29)

    assert check_dpd_bucket_movement(facts) is None

from nbfc_ews.domain.signals import check_bounce_pattern


def test_two_bounces_fires():
    facts = AccountFacts(account_id="A1", dpd=0, dpd_last_month=0, bounces_last_3m=2)

    assert check_bounce_pattern(facts) is not None


def test_one_bounce_with_retries_fires():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0,
        bounces_last_3m=1, retries_on_last_bounce=2,
    )

    assert check_bounce_pattern(facts) is not None


def test_one_clean_bounce_does_not_fire():
    facts = AccountFacts(account_id="A1", dpd=0, dpd_last_month=0, bounces_last_3m=1)

    assert check_bounce_pattern(facts) is None

def test_evaluate_returns_both_signals():
    facts = AccountFacts(
        account_id="A1", dpd=34, dpd_last_month=12, bounces_last_3m=2,
    )

    signals = evaluate(facts)

    assert len(signals) == 2


def test_evaluate_returns_empty_for_clean_account():
    facts = AccountFacts(account_id="A1", dpd=0, dpd_last_month=0)

    assert evaluate(facts) == []

from nbfc_ews.domain.signals import check_moratorium_ending


def test_moratorium_ending_soon_fires():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0, days_to_moratorium_end=60,
    )

    assert check_moratorium_ending(facts) is not None


def test_moratorium_far_away_does_not_fire():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0, days_to_moratorium_end=200,
    )

    assert check_moratorium_ending(facts) is None


def test_no_moratorium_does_not_fire():
    facts = AccountFacts(account_id="A1", dpd=0, dpd_last_month=0)

    assert check_moratorium_ending(facts) is None

from nbfc_ews.domain.signals import check_payment_date_drift


def test_payment_drifting_later_fires():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0,
        payment_days_last_3m=(3, 9, 14),
    )

    assert check_payment_date_drift(facts) is not None


def test_small_drift_does_not_fire():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0,
        payment_days_last_3m=(3, 5, 8),
    )

    assert check_payment_date_drift(facts) is None


def test_improving_payment_dates_does_not_fire():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0,
        payment_days_last_3m=(14, 9, 3),
    )

    assert check_payment_date_drift(facts) is None

from nbfc_ews.domain.signals import check_part_payment


def test_two_part_payments_fires():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0,
        paid_ratio_last_3m=(1.0, 0.6, 0.7),
    )

    assert check_part_payment(facts) is not None


def test_full_payments_do_not_fire():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0,
        paid_ratio_last_3m=(1.0, 1.0, 1.0),
    )

    assert check_part_payment(facts) is None


def test_zero_payment_does_not_fire_here():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0,
        paid_ratio_last_3m=(1.0, 0.0, 0.0),
    )

    assert check_part_payment(facts) is None

from nbfc_ews.domain.signals import check_drift_with_bounce


def test_drift_plus_bounce_fires():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0,
        payment_days_last_3m=(3, 9, 14), bounces_last_3m=1,
    )

    assert check_drift_with_bounce(facts) is not None


def test_drift_without_bounce_does_not_fire():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0,
        payment_days_last_3m=(3, 9, 14),
    )

    assert check_drift_with_bounce(facts) is None

from nbfc_ews.domain.signals import check_interest_not_serviced


def test_unserviced_interest_in_moratorium_fires():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0,
        in_moratorium=True, months_interest_unserviced=2,
    )

    assert check_interest_not_serviced(facts) is not None


def test_unserviced_interest_outside_moratorium_does_not_fire():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0,
        in_moratorium=False, months_interest_unserviced=3,
    )

    assert check_interest_not_serviced(facts) is None

from nbfc_ews.domain.signals import check_bureau_deterioration


def test_score_drop_fires():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0,
        bureau_score_prev=720, bureau_score_now=670,
    )

    assert check_bureau_deterioration(facts) is not None


def test_enquiry_burst_fires_without_score():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0, new_enquiries_60d=3,
    )

    assert check_bureau_deterioration(facts) is not None


def test_small_score_drop_does_not_fire():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0,
        bureau_score_prev=720, bureau_score_now=700,
    )

    assert check_bureau_deterioration(facts) is None

from nbfc_ews.domain.signals import check_tranche_not_requested


def test_tranche_overdue_fires():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0, days_past_expected_tranche=45,
    )

    assert check_tranche_not_requested(facts) is not None


def test_tranche_recently_due_does_not_fire():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0, days_past_expected_tranche=10,
    )

    assert check_tranche_not_requested(facts) is None

from nbfc_ews.domain.signals import check_contactability_decay


def test_two_failed_contacts_fires():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0, failed_contacts_60d=2,
    )

    assert check_contactability_decay(facts) is not None


def test_one_failed_contact_does_not_fire():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0, failed_contacts_60d=1,
    )

    assert check_contactability_decay(facts) is None

from nbfc_ews.domain.signals import check_adverse_event


def test_adverse_event_fires():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0, adverse_event="visa_rejected",
    )

    assert check_adverse_event(facts) is not None


def test_no_event_does_not_fire():
    facts = AccountFacts(account_id="A1", dpd=0, dpd_last_month=0)

    assert check_adverse_event(facts) is None

from nbfc_ews.domain.signals import check_institution_cohort


def _flagged(account_id, institution_id):
    return AccountFacts(
        account_id=account_id, dpd=0, dpd_last_month=0,
        institution_id=institution_id,
    )


def test_moratorium_already_ended_does_not_fire():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0, days_to_moratorium_end=-400,
    )

    assert check_moratorium_ending(facts) is None

def test_part_payment_does_not_fire_in_moratorium():
    facts = AccountFacts(
        account_id="A1", dpd=0, dpd_last_month=0,
        in_moratorium=True, paid_ratio_last_3m=(0.35, 0.36, 0.37),
    )

    assert check_part_payment(facts) is None

def test_every_rule_has_a_distinct_signal_type():
    from nbfc_ews.domain.signals import _RULES

    facts = AccountFacts(
        account_id="A1", dpd=34, dpd_last_month=12,
        bounces_last_3m=2, retries_on_last_bounce=2,
        days_to_moratorium_end=10,
        payment_days_last_3m=(3, 9, 14),
        paid_ratio_last_3m=(1.0, 0.6, 0.7),
        in_moratorium=True, months_interest_unserviced=3,
        bureau_score_prev=720, bureau_score_now=650,
        new_enquiries_60d=4,
        days_past_expected_tranche=40,
        failed_contacts_60d=3,
        adverse_event="visa_rejected",
    )

    results = [r(facts) for r in _RULES]
    types = [s.signal_type for s in results if s is not None]

    assert len(types) == len(set(types)), f"duplicate signal_type: {types}"


def test_five_from_one_institution_fires():
    flagged = [_flagged(f"A{i}", "INST-1") for i in range(5)]
    others = [_flagged(f"B{i}", "INST-2") for i in range(95)]

    result = check_institution_cohort(flagged, flagged + others)

    assert len(result) == 1
    assert result[0].institution_id == "INST-1"


def test_four_from_one_institution_does_not_fire():
    flagged = [_flagged(f"A{i}", "INST-1") for i in range(4)]
    others = [_flagged(f"B{i}", "INST-2") for i in range(96)]

    assert check_institution_cohort(flagged, flagged + others) == []