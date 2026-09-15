from datetime import date

from nbfc_ews.domain.principal import Principal
from nbfc_ews.llm.base import ToolCall
from nbfc_ews.tools.base import ToolResult, failure
from nbfc_ews.tools.registry import get, tools_for

_INJECTED = {"conn", "principal", "as_of"}

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

    try:
        return tool(conn, principal, as_of=as_of, **call.arguments)
    except TypeError as exc:
        return failure(f"bad argument for {call.name}: {exc}")
