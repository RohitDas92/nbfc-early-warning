from datetime import date

import pytest

from nbfc_ews.db.repositories.policy import load_policy
from nbfc_ews.domain.authority import PolicyError


def test_loads_every_action_at_a_current_date(conn):
    policy = load_policy(conn, date(2026, 6, 1))
    assert len(policy.rules) == 9
    assert len(policy.slabs) == 3


def test_a_date_before_any_rule_takes_effect_has_no_policy(conn):
    with pytest.raises(PolicyError, match="no active rule"):
        load_policy(conn, date(2018, 12, 31))