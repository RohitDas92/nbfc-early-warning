from datetime import date

from nbfc_ews.domain.actions import Precondition
from nbfc_ews.domain.authority import Policy, Slab

_RULES_SQL = """
select action_type, min_dpd, max_dpd, requires_prior, forbidden_when,
       authority, source_clause
from action_policy
where effective_from <= %(as_of)s
  and (effective_to is null or effective_to > %(as_of)s)
"""

_SLABS_SQL = """
select waiver_type, min_amount, max_amount, authority, source_clause
from waiver_slab
where effective_from <= %(as_of)s
  and (effective_to is null or effective_to > %(as_of)s)
order by waiver_type, min_amount
"""


def load_policy(conn, as_of: date) -> Policy:
    """Every rule in force on as_of. Called once per run, never per case."""
    rules = [
        Precondition(
            action=action,
            min_dpd=min_dpd,
            max_dpd=max_dpd,
            requires_prior=tuple(requires_prior or ()),
            forbidden_when=tuple(forbidden_when or ()),
            authority=authority,
            source_clause=source_clause,
        )
        for (
            action,
            min_dpd,
            max_dpd,
            requires_prior,
            forbidden_when,
            authority,
            source_clause,
        ) in conn.execute(_RULES_SQL, {"as_of": as_of})
    ]

    slabs = [
        Slab(
            waiver_type=waiver_type,
            min_amount=min_amount,
            max_amount=max_amount,
            authority=authority,
            source_clause=source_clause,
        )
        for (
            waiver_type,
            min_amount,
            max_amount,
            authority,
            source_clause,
        ) in conn.execute(_SLABS_SQL, {"as_of": as_of})
    ]

    return Policy.build(rules, slabs)