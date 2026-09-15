from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from nbfc_ews.llm.base import Message, ModelReply, ToolCall, ToolSpec, Usage


class ScriptExhausted(Exception):
    """The fake was asked for more replies than the script provides."""

def says(text: str) -> ModelReply:
    """A reply with no tool calls - the model answering."""
    return ModelReply(
        text= text,
        tool_calls= (),
        usage= Usage(input_tokens=100, output_tokens=len(text.split())),
        model = "fake",
    )

def calls_tool(name: str, call_id: str = "c1", **arguments: Any) -> ModelReply:
    """A reply asking for one tool to be run."""
    return ModelReply(
        text=None,
        tool_calls=(ToolCall(id=call_id, name=name, arguments=arguments),),
        usage=Usage(input_tokens=100, output_tokens=20),
        model="fake",
    )

@dataclass
class FakeChatModel:
    """Replays a fixed list of replies, im order. No network, no cost, no surprises."""

    script: list[ModelReply]
    calls: list[list[Message]] = field(default_factory=list)
    _next: int = 0

    @property
    def name(self) -> str:
        return "fake"

    def complete(
            self,
            messages: Sequence[Message],
            tools: Sequence[ToolSpec] = (),           
    ) -> ModelReply:
        if self._next >= len(self.script):
            raise ScriptExhausted(
                f"script has {len(self.script)} replies: this is call (self._next + 1)"
            )

        self.calls.append(list(messages))
        reply = self.script[self._next]
        self._next += 1
        return reply


    