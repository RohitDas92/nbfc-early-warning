import json
from dataclasses import dataclass

from nbfc_ews.agents.context import CaseContext
from nbfc_ews.agents.dispatch import dispatch, effective_arguments
from nbfc_ews.domain.principal import Principal
from nbfc_ews.llm.base import ChatModel, Message, ToolSpec
from nbfc_ews.tools.base import ToolResult
from nbfc_ews.tools.registry import tools_for

_SYSTEM = (
    "You are the {agent} investigator for an education-loan NBFC's early warning"
    " system. The business date is {as_of}; every tool answers as of that date and"
    " no later data exists. Use your tools to gather evidence, then state what you"
    " found in three sentences or fewer. Report only what the tool results support,"
    " and say so plainly if the evidence is thin. Do not recommend an action -"
    " another agent decides that."
)

@dataclass(frozen=True)
class Finding:
    """What one investigator concluded, and what it cost to get there."""

    agent: str
    text: str | None
    complete: bool
    turns: int
    tool_calls: int
    input_tokens: int
    output_tokens: int

def specs_for(agent: str) -> list[ToolSpec]:
    """What this agent's tools look like to a model."""
    return[
        ToolSpec(
            name= tool.name,
            description=tool.description,
            parameters=tool.parameters,
        ) for tool in tools_for(agent)
    ]

def _as_text(result: ToolResult) -> str:
    """A tool result, as the model will read it.""" 
    if not result.ok:
        return json.dumps({"ok": False, "reason": result.reason})

    return json.dumps(
        {
            "ok": True,
            "as_of": result.as_of.isoformat() if result.as_of else None,
            "omitted": result.omitted,
            "data": result.data
        }   
    )

def investigate(
        agent: str,
        question: str,
        model: ChatModel,
        ctx: CaseContext,
        conn,
        principal: Principal,
        max_turns: int = 6,
) -> Finding:
    """Ask, run tools, ask again - untill the model answers or the budget runs out."""
    messages: list[Message] = [
        Message(role="system", content=_SYSTEM.format(agent=agent, as_of= ctx.as_of)),
        Message(role="user", content= question),
    ]

    specs = specs_for(agent)

    turns = 0
    tool_calls = 0
    input_tokens = 0
    output_tokens = 0

    while turns < max_turns:
        turns += 1

        reply = model.complete(messages, specs)
        input_tokens += reply.usage.input_tokens
        output_tokens += reply.usage.output_tokens

        if not reply.tool_calls:
            return Finding(
                agent=agent,
                text=reply.text,
                complete=True,
                turns=turns,
                tool_calls=tool_calls,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        messages.append(
            Message(role="assistant", content=reply.text or "", tool_calls=reply.tool_calls
                    ))

        for call in reply.tool_calls:
            # Normalised once: the cache, the call and the log all use this.
            arguments = effective_arguments(call)
            cached = ctx.read(call.name, **arguments)
            if cached is not None:
                result = cached
            else:   
                result =dispatch(call, agent, conn, principal, ctx.as_of)
                ctx.record(agent, call.name, arguments, result)
                tool_calls += 1

            messages.append(
                Message(role="tool", content= _as_text(result), tool_call_id=call.id)
            )
    return Finding(
        agent = agent,
        text = None,
        complete=False,
        turns=turns,
        tool_calls=tool_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens
    )

