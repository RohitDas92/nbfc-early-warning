from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from nbfc_ews.tools.base import ToolResult


def _key(arguments: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    """Arguments in a fixed order, so two calls can be compared."""
    return tuple(sorted(arguments.items()))

@dataclass(frozen=True)
class Entry:
    """One thing that was found, who found it, and when."""

    agent: str
    tool: str
    arguments: tuple[tuple[str, Any], ...]
    result: ToolResult
    recorded_at: datetime

@dataclass
class CaseContext:
    """Everything found about one case during one investigation."""

    case_id: str
    as_of: date
    _entries: list[Entry] = field(default_factory=list)

    def record(
            self, 
            agent: str,
            tool: str,
            arguments: dict[str, Any],
            result: ToolResult,
    ) -> None:
        """Append a finding. Never overwrites - the log keeps everything."""
        self._entries.append(
            Entry(
                agent=agent,
                tool=tool,
                arguments= _key(arguments),
                result=result,
                recorded_at=datetime.now(UTC),
            )
        )

    def read(self, tool: str, **arguments: Any) -> ToolResult | None:
        """The successful result of this exact call, if anyone made it."""
        want = _key(arguments)
        for entry in self._entries:
            if entry.tool == tool and entry.arguments == want and entry.result.ok:
                return entry.result
            return None
        return None

    def entries(self) -> tuple[Entry, ...]:
        """The whole log, in order, for the trace and the citations."""
        return tuple(self._entries)

    