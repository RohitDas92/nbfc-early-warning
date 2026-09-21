"""Strict mode sends "not given" as null.  A tool must never receive it."""

from datetime import date
from typing import Any

import nbfc_ews.tools  # noqa: F401  - registers the real tools
from nbfc_ews.agents import dispatch as dispatch_module
from nbfc_ews.agents.context import CaseContext
from nbfc_ews.agents.dispatch import dispatch, effective_arguments
from nbfc_ews.llm.base import ToolCall
from nbfc_ews.tools.base import ToolResult, success


class Echo:
    """A stand-in tool that records exactly what it was called with."""

    name = "echo"

    def __init__(self) -> None:
        self.received: dict[str, Any] = {}

    def __call__(self, conn, principal, as_of: date, **kwargs: Any) -> ToolResult:
        self.received = kwargs
        return success([], as_of)


def test_null_arguments_are_dropped_so_the_tools_default_applies(monkeypatch) -> None:
    tool = Echo()
    monkeypatch.setattr(dispatch_module, "get", lambda name: tool)
    monkeypatch.setattr(dispatch_module, "tools_for", lambda agent: [tool])

    call = ToolCall(id="c1", name="echo", arguments={"account_id": "A-1", "limit": None})
    result = dispatch(call, "repayment", None, None, date(2026, 9, 1))

    assert result.ok
    assert tool.received == {"account_id": "A-1"}


def test_real_values_pass_through_untouched(monkeypatch) -> None:
    tool = Echo()
    monkeypatch.setattr(dispatch_module, "get", lambda name: tool)
    monkeypatch.setattr(dispatch_module, "tools_for", lambda agent: [tool])

    call = ToolCall(id="c1", name="echo", arguments={"account_id": "A-1", "limit": 0})
    dispatch(call, "repayment", None, None, date(2026, 9, 1))

    assert tool.received == {"account_id": "A-1", "limit": 0}

# --- effective arguments: what actually runs ---------------------------------

def test_a_null_is_replaced_by_the_tools_own_default() -> None:
    call = ToolCall(id="c1", name="get_payment_behaviour",
                    arguments={"account_id": "A-1", "months": None})

    assert effective_arguments(call) == {"account_id": "A-1", "months": 12}


def test_null_and_the_explicit_default_are_the_same_call() -> None:
    as_null = ToolCall(id="c1", name="get_payment_behaviour",
                       arguments={"account_id": "A-1", "months": None})
    as_twelve = ToolCall(id="c2", name="get_payment_behaviour",
                         arguments={"account_id": "A-1", "months": 12})

    assert effective_arguments(as_null) == effective_arguments(as_twelve)


def test_a_cached_result_is_found_whichever_way_the_default_was_asked_for() -> None:
    """The bug this fixes: months=None missed a cache entry recorded as months=12."""
    ctx = CaseContext(case_id="T", as_of=date(2026, 7, 1))
    first = ToolCall(id="c1", name="get_payment_behaviour",
                     arguments={"account_id": "A-1", "months": 12})
    again = ToolCall(id="c2", name="get_payment_behaviour",
                     arguments={"account_id": "A-1", "months": None})

    ctx.record("repayment", first.name, effective_arguments(first), success([], ctx.as_of))

    assert ctx.read(again.name, **effective_arguments(again)) is not None


def test_injected_parameters_never_appear_in_the_log() -> None:
    call = ToolCall(id="c1", name="get_bureau_history", arguments={"account_id": "A-1"})

    assert set(effective_arguments(call)) == {"account_id", "limit"}
