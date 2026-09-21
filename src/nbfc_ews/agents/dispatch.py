import inspect
from datetime import date
from typing import Any

from nbfc_ews.domain.principal import Principal
from nbfc_ews.llm.base import ToolCall
from nbfc_ews.tools.base import ToolResult, failure
from nbfc_ews.tools.registry import get, tools_for

_INJECTED = {"conn", "principal", "as_of"}


def effective_arguments(call: ToolCall) -> dict[str, Any]:
    """What the tool will actually run with: nulls dropped, its own defaults filled in.

    Strict mode sends "not given" as null, so months=None and months=12 are the
    same query.  This is the one place that says so - used for the call, the
    cache key and the evidence log, so all three always agree.
    """
    given = {key: value for key, value in call.arguments.items() if value is not None}
    tool = get(call.name)
    if tool is None:
        return given  # dispatch reports the unknown tool

    signature = inspect.signature(tool)
    try:
        bound = signature.bind_partial(**given)
    except TypeError:
        return given  # an argument the tool does not take: dispatch reports it
    bound.apply_defaults()

    effective: dict[str, Any] = {}
    for name, value in bound.arguments.items():
        if signature.parameters[name].kind is inspect.Parameter.VAR_KEYWORD:
            effective.update(value)
        elif name not in _INJECTED:
            effective[name] = value
    return effective

def dispatch(
        call: ToolCall,
        agent: str,
        conn,
        principal: Principal,
        as_of: date,
) ->  ToolResult:
    """Run a tool that model asked for - if this agent has allowed it."""
    allowed = {tool.name for tool in tools_for(agent)}
    if call.name not in allowed:
        return failure(f"no tool name {call.name!r} is available")

    tool = get(call.name)
    if tool is None:
        return failure(f"no tool named {call.name!r} is available")

    if set(call.arguments) & _INJECTED:
        return failure("conn, principal and as_of are supplied by system")


    arguments = effective_arguments(call)

    try:
        return tool(conn, principal, as_of=as_of, **arguments)
    except TypeError as exc:
        return failure(f"bad argument for {call.name}: {exc}")
