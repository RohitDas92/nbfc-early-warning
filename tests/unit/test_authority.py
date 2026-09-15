from decimal import Decimal
from typing import get_args

import pytest

from nbfc_ews.domain.actions import (
    ActionFacts,
    ActionRequest,
    ActionType,
    Precondition,
)
from nbfc_ews.domain.authority import Policy, PolicyError, Slab

SLABS = [
    Slab("interest", Decimal(0), Decimal(25000), "manager", "SP 2.1"),
    Slab("interest", Decimal(25000), Decimal(100000), "head", "SP 2.2"),
    Slab("interest", Decimal(100000), None, "committee", "SP 2.3"),
]

CLEAN = ActionFacts(dpd=0, in_moratorium=False, prior_actions=frozenset())


def rule(action, min_dpd=0, max_dpd=None, requires_prior=(),
         forbidden_when=(), authority="analyst"):
    return Precondition(
        action=action,
        min_dpd=min_dpd,
        max_dpd=max_dpd,
        requires_prior=requires_prior,
        forbidden_when=forbidden_when,
        authority=authority,
        source_clause="SOP 1.1",
    )


def full_rules():
    """One default rule per action, so build() succeeds."""
    return [rule(a) for a in get_args(ActionType)]


def policy_with(action, **overrides):
    """Every action at defaults, except one."""
    return Policy.build(
        [rule(a, **overrides) if a == action else rule(a)
         for a in get_args(ActionType)],
        SLABS,
    )


def facts(dpd=0, in_moratorium=False, prior=()):
    return ActionFacts(dpd=dpd, in_moratorium=in_moratorium,
                       prior_actions=frozenset(prior))


# --- the builder -------------------------------------------------------------

def test_build_refuses_a_missing_action():
    with pytest.raises(PolicyError, match="no active rule"):
        Policy.build(full_rules()[:-1], SLABS)


def test_build_refuses_two_rules_for_one_action():
    with pytest.raises(PolicyError, match="two active rules"):
        Policy.build(full_rules() + [rule("FIELD_VISIT")], SLABS)


# --- state preconditions -----------------------------------------------------

def test_below_min_dpd_is_denied():
    d = policy_with("FIELD_VISIT", min_dpd=45).check(
        ActionRequest("FIELD_VISIT"), facts(dpd=30)
    )
    assert d is not None
    assert "45" in d.reason
    assert d.rule == "SOP 1.1"


def test_at_min_dpd_is_permitted():
    d = policy_with("FIELD_VISIT", min_dpd=45).check(
        ActionRequest("FIELD_VISIT"), facts(dpd=45)
    )
    assert d is None


def test_above_max_dpd_is_denied():
    d = policy_with("MORATORIUM_EXTENSION", max_dpd=30).check(
        ActionRequest("MORATORIUM_EXTENSION"), facts(dpd=31)
    )
    assert d is not None


def test_moratorium_blocks_a_forbidden_action():
    d = policy_with("FIELD_VISIT", forbidden_when=("in_moratorium",)).check(
        ActionRequest("FIELD_VISIT"), facts(dpd=90, in_moratorium=True)
    )
    assert d is not None
    assert "moratorium" in d.reason


def test_missing_prerequisite_is_denied_and_named():
    d = policy_with(
        "CONTACT_CO_APPLICANT", requires_prior=("SOFT_CONTACT_BORROWER",)
    ).check(ActionRequest("CONTACT_CO_APPLICANT"), CLEAN)
    assert d is not None
    assert "SOFT_CONTACT_BORROWER" in d.reason


def test_satisfied_prerequisite_is_permitted():
    d = policy_with(
        "CONTACT_CO_APPLICANT", requires_prior=("SOFT_CONTACT_BORROWER",)
    ).check(
        ActionRequest("CONTACT_CO_APPLICANT"),
        facts(prior=("SOFT_CONTACT_BORROWER",)),
    )
    assert d is None


def test_permitted_excludes_what_check_denies():
    p = policy_with("FIELD_VISIT", min_dpd=45)
    assert "FIELD_VISIT" not in p.permitted(facts(dpd=30))
    assert "FIELD_VISIT" in p.permitted(facts(dpd=60))


# --- waivers -----------------------------------------------------------------

def test_a_principal_waiver_can_never_be_approved():
    p = policy_with("SETTLEMENT", authority=None)
    request = ActionRequest("SETTLEMENT", "principal", Decimal(1))

    assert p.check(request, CLEAN) is not None
    assert p.authority_for(request) is None


def test_settlement_without_waiver_details_is_refused():
    d = policy_with("SETTLEMENT", authority=None).check(
        ActionRequest("SETTLEMENT"), CLEAN
    )
    assert d is not None
    assert "waiver" in d.reason


def test_a_zero_waiver_is_refused():
    d = policy_with("SETTLEMENT", authority=None).check(
        ActionRequest("SETTLEMENT", "interest", Decimal(0)), CLEAN
    )
    assert d is not None


@pytest.mark.parametrize(
    "amount,expected",
    [
        ("1", "manager"),
        ("25000", "manager"),
        ("25000.01", "head"),
        ("100000", "head"),
        ("100000.01", "committee"),
        ("5000000", "committee"),
    ],
)
def test_slab_boundaries(amount, expected):
    got = policy_with("SETTLEMENT", authority=None).authority_for(
        ActionRequest("SETTLEMENT", "interest", Decimal(amount))
    )
    assert got == expected


def test_an_action_with_its_own_authority_ignores_slabs():
    p = policy_with("FIELD_VISIT", authority="manager")
    assert p.authority_for(ActionRequest("FIELD_VISIT")) == "manager"

