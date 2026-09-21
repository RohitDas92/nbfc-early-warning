"""Every tool's schema must be acceptable to Azure in strict mode.

A schema that breaks these rules fails with a 400 on the first live call,
not in any unit test - so the rules are checked here, for every tool at once.
A fifth tool added next month is checked automatically.
"""

import re

import pytest

import nbfc_ews.tools  # noqa: F401  - importing the package registers the tools
from nbfc_ews.tools.registry import all_tools

TOOLS = all_tools()
NAME = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def test_there_are_tools_to_check() -> None:
    assert TOOLS, "no tools registered - every check below would pass vacuously"


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_the_name_is_one_azure_accepts(tool) -> None:
    assert NAME.match(tool.name)


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_the_schema_is_a_closed_object(tool) -> None:
    schema = tool.parameters

    assert schema["type"] == "object"
    assert schema.get("additionalProperties") is False


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_every_property_is_required(tool) -> None:
    """Strict mode's rule. Optional means nullable, not absent."""
    schema = tool.parameters

    assert set(schema["required"]) == set(schema["properties"])


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_no_property_carries_a_default(tool) -> None:
    """The default lives in the Python signature. One source of truth."""
    for name, prop in tool.parameters["properties"].items():
        assert "default" not in prop, f"{tool.name}.{name} has a schema default"


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_every_property_declares_a_type(tool) -> None:
    for name, prop in tool.parameters["properties"].items():
        assert "type" in prop, f"{tool.name}.{name} has no type"