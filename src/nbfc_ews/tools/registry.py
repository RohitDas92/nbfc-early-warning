from nbfc_ews.tools.base import Tool

_REGISTRY: dict[str, Tool] = {}

_AGENT_TOOLS: dict[str, set[str]] = {
    "repayment": {"get_payment_behaviour","find_similar_alerts"},
    "external": set(),
    "context": set(),
    "cohort": set(),
    "policy": set(),
    "bureau": {"get_bureau_history"}
}

def register(tool: Tool) -> None:
    """Add a tool. Name must be unique."""
    if tool.name in _REGISTRY:
        raise ValueError(f"tool already registered: {tool.name}")
    _REGISTRY[tool.name] = tool

def get(name: str) -> Tool | None:
    """Look a tool up by name. None if it dose not exist."""
    return _REGISTRY.get(name)

def tools_for(agent: str) -> list[Tool]:
    """The tools this agent is permited to use. unknown agent gets none."""
    allowed = _AGENT_TOOLS.get(agent, set())
    return [_REGISTRY[name] for name in sorted(allowed) if name in _REGISTRY]

