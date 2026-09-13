from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: list[dict[str, Any]] = field(default_factory=list)
    as_of: date | None = None
    omitted: int = 0
    reason: str | None = None

def success(data: list[dict], as_of: date | None, omitted: int = 0) -> ToolResult:
    """A Tool answered the question."""
    return ToolResult(ok = True, data = data, as_of= as_of , omitted=omitted)

def failure(reason: str) -> ToolResult:
    """A tool could not answer, and this is the reason."""
    return ToolResult(ok = False, reason=reason)

class Tool(Protocol):
    """The shape every tool must have."""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    def __call__(self, *args: Any, **kwargs: Any) -> ToolResult: ...

