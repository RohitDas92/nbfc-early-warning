from datetime import date

import pytest

from nbfc_ews.tools import registry
from nbfc_ews.tools.base import ToolResult, failure, success


class _FakeTool:
    name = "get_payment_behaviour"
    description = "test double"

    def __call__(self, conn, principal, **params) -> ToolResult:
        return success(data=[{"paid": 1}], as_of=date(2026, 6, 1))


@pytest.fixture(autouse=True)
def clean_registry():
    """The registry is module-level state — reset it around every test."""
    registry._REGISTRY.clear()
    yield
    registry._REGISTRY.clear()


def test_success_has_no_reason():
    r = success(data=[{"a": 1}], as_of=date(2026, 6, 1))

    assert r.ok is True
    assert r.reason is None


def test_failure_has_no_data():
    r = failure("account not found")

    assert r.ok is False
    assert r.data == []
    assert r.reason == "account not found"


def test_register_then_get():
    tool = _FakeTool()
    registry.register(tool)

    assert registry.get("get_payment_behaviour") is tool


def test_duplicate_name_is_refused():
    registry.register(_FakeTool())

    with pytest.raises(ValueError):
        registry.register(_FakeTool())


def test_unknown_tool_returns_none():
    assert registry.get("no_such_tool") is None


def test_agent_gets_only_its_permitted_tools():
    registry.register(_FakeTool())

    assert [t.name for t in registry.tools_for("repayment")] == ["get_payment_behaviour"]
    assert registry.tools_for("policy") == []


def test_unknown_agent_gets_nothing():
    registry.register(_FakeTool())

    assert registry.tools_for("intruder") == []