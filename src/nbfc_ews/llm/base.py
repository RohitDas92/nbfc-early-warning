from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

MessageRole = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class ToolCall:
    """The model asking for a tool to be run. It has not been run yet."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Message:
    """One turn in a conversation with a model.

    An assistant message that asked for tools must carry those calls, so the
    tool results that follow it can be matched back. Without them the API
    rejects the next request: a tool result with nothing to answer.
    """

    role: MessageRole
    content: str
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class ModelReply:
    """What came back from one call."""

    text: str | None
    tool_calls: tuple[ToolCall, ...]
    usage: Usage
    model: str


@dataclass(frozen=True)
class ToolSpec:
    """What the model is *told* about a tool. Not the tool itself."""

    name: str
    description: str
    parameters: dict[str, Any]


class ChatModel(Protocol):
    """Anything that can be asked a question. Fake or real."""

    @property
    def name(self) -> str: ...

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] = (),
    ) -> ModelReply: ...