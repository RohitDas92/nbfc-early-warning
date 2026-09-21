"""One real round trip against Azure.  Costs money, needs the network.

Skipped unless EWS_LIVE_AZURE=1, so a normal pytest run never calls Azure.
"""

import os

import pytest

from nbfc_ews.llm.azure_openai import AzureChatModel
from nbfc_ews.llm.base import Message, ToolSpec

pytestmark = pytest.mark.skipif(
    os.environ.get("EWS_LIVE_AZURE") != "1",
    reason="set EWS_LIVE_AZURE=1 to call real Azure",
)

TOOL = ToolSpec(
    name="get_dpd",
    description="Days past due for one loan account, as of the business date.",
    parameters={
        "type": "object",
        "properties": {"loan_id": {"type": "string"}},
        "required": ["loan_id"],
        "additionalProperties": False,
    },
)


def test_a_full_tool_round_trip_against_azure() -> None:
    model = AzureChatModel()
    history = [
        Message(role="system", content="You are a collections investigator. Use your tools; never guess."),
        Message(role="user", content="What is the DPD on loan L-1001?"),
    ]

    first = model.complete(history, [TOOL])
    assert len(first.tool_calls) == 1
    call = first.tool_calls[0]
    assert call.arguments == {"loan_id": "L-1001"}

    history += [
        Message(role="assistant", content=first.text or "", tool_calls=first.tool_calls),
        Message(role="tool", content='{"ok": true, "dpd": 47}', tool_call_id=call.id),
    ]

    second = model.complete(history, [TOOL])
    assert second.tool_calls == ()
    assert "47" in (second.text or "")