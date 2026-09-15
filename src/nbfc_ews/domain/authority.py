from dataclasses import dataclass
from decimal import Decimal
from typing import get_args

from nbfc_ews.domain.actions import (
    ActionFacts,
    ActionRequest,
    ActionType,
    Authority,
    Denial,
    Precondition,
)


class PolicyError(Exception):
    """The loaded policy is unuseable. Fail at load, not at use."""

@dataclass(frozen= True)
class Slab:
    waiver_type: str
    min_amount: Decimal
    max_amount: Decimal | None
    authority: Authority
    source_clause: str | None

@dataclass(frozen= True)
class Policy:
    """Every rule in force on one date, Built once per run."""

    rules: dict[ActionType, Precondition]
    slabs: tuple[Slab, ...]

    @staticmethod
    def build(rules: list[Precondition], slabs: list[Slab]) -> "Policy":
        by_action: dict[ActionType, Precondition] = {}

        for rule in rules:
            if rule.action in by_action:
                raise PolicyError(f"two active rules for {rule.action}")
            by_action[rule.action] = rule

        missing = set(get_args(ActionType)) - set(by_action)
        if missing:
            raise PolicyError(f"no active rule for: {sorted(missing)}")

        return Policy(rules=by_action, slabs=tuple(slabs))
        
    def _precondition_denial(
            self, action: ActionType, facts: ActionFacts
    ) -> Denial | None:
        """State-bases checks only - nothing that depends on parameters."""
        rule = self.rules.get(action)
        if rule is None:
            return Denial(action, "no rule permit this action", None)

        if rule.min_dpd is not None and facts.dpd < rule.min_dpd:
            return Denial(
                action,
                f"required DPD of at least {rule.min_dpd}; account is at {facts.dpd}",
                rule.source_clause,
            )

        if rule.max_dpd is not None and facts.dpd > rule.max_dpd:
            return Denial(
                action, 
                f"not permitted above DPD {rule.max_dpd}; account is at {facts.dpd}",
                rule.source_clause,
            )

        if "in_moratorium" in rule.forbidden_when and facts.in_moratorium:
            return Denial(action, "not permitted during moratorium", rule.source_clause)

        missing = [a for a in rule.requires_prior if a not in facts.prior_actions]
        if missing:
            return Denial(
                action,
                f"requires {', '.join(missing)} to be attempted first",
                rule.source_clause,
            )
        return None

    def _slab_for(self, waiver_type: str, amount: Decimal) -> Slab | None:
        """Exclusive low, inclusive high: 25000 is manager, 25000.01 is head."""
        for slab in self.slabs:
            if slab.waiver_type != waiver_type:
                continue
            if amount > slab.min_amount and (slab.max_amount is None or amount <= slab.max_amount):
                return slab

        return None

    def check(self, request: ActionRequest, facts: ActionFacts) -> Denial | None:
        """None means permitted. A denial names the rule that refused it."""

        denial = self._precondition_denial(request.action, facts)
        if denial is not None:
            return denial

        rule = self.rules[request.action]
        if rule.authority is not None:
            return None

        #authority is null -> it comes from a slab, by amount
        if request.waiver_type is None or request.waiver_amount is None:
            return Denial(
                request.action,
                "a waiver type and amount are required",
                rule.source_clause,
            )

        if request.waiver_amount <= 0:
            return Denial(
                request.action, "waiver amount must be positive", rule.source_clause
            )

        if self._slab_for(request.waiver_type, request.waiver_amount) is None:
            return Denial(
                request.action,
                f"no approval authority exits for a {request.waiver_type} "
                f"waiver of {request.waiver_amount}",
                rule.source_clause,
            )

        return None

    def permitted(self, facts: ActionFacts) -> set[ActionType]:
        """Actions whose state preconditions are met - the set given to the model."""

        return {
            action 
            for action in self.rules 
            if self._precondition_denial(action, facts) is None
        }

    def authority_for(self, request: ActionRequest) -> Authority | None:
        """Who must approve this, once it has passed check()."""
        rule = self.rules[request.action]
        if rule.authority is not None:
            return rule.authority

        if request.waiver_type is None or request.waiver_amount is None:
            return None

        slab = self._slab_for(request.waiver_type, request.waiver_amount)
        return slab.authority if slab else None
