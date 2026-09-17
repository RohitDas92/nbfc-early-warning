from dataclasses import dataclass

from nbfc_ews.agents.context import CaseContext
from nbfc_ews.agents.investigate import Finding, investigate
from nbfc_ews.domain.principal import Principal
from nbfc_ews.llm.base import ChatModel

_DEFAULT: tuple[str, ...] = ("repayment",)

_PLAN: dict[str, tuple[str, ...]] = {
    "bounce_pattern":        ("repayment",),
    "payment_date_drift":    ("repayment",),
    "drift_with_bounce":     ("repayment",),
    "part_payment":          ("repayment",),
    "interest_not_serviced": ("repayment",),
    "moratorium_ending":     ("repayment",),
    "contactability_decay":  ("repayment",),
    "bureau_deterioration":  ("bureau",),
    "dpd_bucket_movement":   ("repayment","bureau",),
    "adverse_event":         ("repayment","bureau",),
    "tranche_not_requested": ("repayment","bureau",),
}

_Questions: dict[str, str] ={
    "repayment": (
        "Account {account_id} was flagged for {signals}."
        " Is repayment deteriorating, and what has worked on accounts like this?" 
    ),
    "bureau": (
        "Account {account_id} was flagged for {signals}, "
        " Is there credit stress on this borrower outside this loan?"
    ),
}

@dataclass(frozen=True)
class Supervision:
    """One investigation of one case, and what it cost."""

    case_id: str
    agents_run: tuple[str, ...]
    findings: tuple[Finding, ...]
    complete: bool
    input_tokens: int
    output_tokens: int

def plan(signal_types: list[str]) -> list[str]:
    """Which investigators this case needs. Deterministic - no model involved."""
    chosen: list[str] = []
    for signal_type in signal_types:
        for agent in _PLAN.get(signal_type, _DEFAULT):
            if agent not in chosen:
                chosen.append(agent)
    return chosen

def supervise(
        case_id: str,
        account_id: str,
        signal_types: list[str],
        model: ChatModel,
        ctx: CaseContext,
        conn,
        principal: Principal,
) -> Supervision:
    """Run the investigators this case needs and pool what they found."""
    agents = plan(signal_types)
    signals = ", ". join(signal_types)

    findings: list[Finding] = []
    for agent in agents:
        findings.append(
            investigate(
                agent=agent,
                question=_Questions[agent].format(
                    account_id=account_id, signals=signals
                ),
                model=model,
                ctx=ctx,
                conn=conn,
                principal=principal,
            )
        )

    return Supervision(
        case_id=case_id,
        agents_run=tuple(agents),
        findings=tuple(findings),
        complete=all(f.complete for f in findings),
        input_tokens=sum(f.input_tokens for f in findings),
        output_tokens=sum(f.output_tokens for f in findings)
    )