"""Strict mode sends "not given" as null.  A tool must never receive it."""

from datetime import date
from typing import Any

from nbfc_ews.agents import dispatch as dispatch_module
from nbfc_ews.agents.dispatch import dispatch
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