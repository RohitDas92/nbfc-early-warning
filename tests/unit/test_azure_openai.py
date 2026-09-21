"""Contracts for the Azure adapter.

No network.  A fake transport stands in for HTTP, and the canned responses are
trimmed copies of what probe_chat.py actually got back from Azure - so these
tests pin the adapter to the real wire format, not to a guess about it.
"""

import json
from typing import Any

import pytest

from nbfc_ews.llm.azure_openai import (
    AzureChatModel,
    ContentBlocked,
    ModelError,
    ModelIncomplete,
    TransportError,
    to_input,
)
from nbfc_ews.llm.base import Message, ToolCall, ToolSpec

# --- fixtures: from the probe, trimmed to the fields the adapter reads --------

TURN_1: dict[str, Any] = {
    "id": "resp_1",
    "status": "completed",
    "model": "gpt-5-mini",
    "content_filters": [{"blocked": False}, {"blocked": False}],
    "output": [
        {"type": "reasoning", "content": [], "summary": []},
        {
            "type": "function_call",
            "status": "completed",
            "arguments": '{"loan_id":"L-1001"}',
            "call_id": "call_Kr2uufyB9FIxiliTOkFHbtQu",
            "name": "get_dpd",
        },
    ],
    "usage": {
        "input_tokens": 81,
        "output_tokens": 150,
        "output_tokens_details": {"reasoning_tokens": 64},
    },
}

TURN_2: dict[str, Any] = {
    "id": "resp_2",
    "status": "completed",
    "model": "gpt-5-mini",
    "content_filters": [{"blocked": False}, {"blocked": False}],
    "output": [
        {
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "output_text", "text": "Days past due (DPD) for loan L-1001 is 47 days."}
            ],
        }
    ],
    "usage": {
        "input_tokens": 125,
        "output_tokens": 22,
        "output_tokens_details": {"reasoning_tokens": 0},
    },
}

TOOL = ToolSpec(
    name="get_dpd",
    description="Days past due for one loan account.",
    parameters={
        "type": "object",
        "properties": {"loan_id": {"type": "string"}},
        "required": ["loan_id"],
        "additionalProperties": False,
    },
)

HISTORY = [
    Message(role="system", content="You are an investigator."),
    Message(role="user", content="What is the DPD on L-1001?"),
]


class FakeTransport:
    """Plays back responses in order.  An exception in the list is raised."""

    def __init__(self, *responses: dict[str, Any] | Exception) -> None:
        self.responses = list(responses)
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, body: dict[str, Any]) -> dict[str, Any]:
        self.bodies.append(body)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def build(transport: FakeTransport, **kwargs: Any) -> tuple[AzureChatModel, list[float]]:
    """A model whose sleep records the delay instead of waiting."""
    delays: list[float] = []
    model = AzureChatModel(
        deployment="gpt-5-mini", transport=transport, sleep=delays.append, **kwargs
    )
    return model, delays


# --- mapping out ------------------------------------------------------------


def test_plain_roles_map_to_role_and_content() -> None:
    assert to_input(HISTORY) == [
        {"role": "system", "content": "You are an investigator."},
        {"role": "user", "content": "What is the DPD on L-1001?"},
    ]


def test_an_assistant_message_with_tool_calls_becomes_function_call_items() -> None:
    """E6.4.  Without this the next request is rejected by Azure."""
    message = Message(
        role="assistant",
        content="Checking both.",
        tool_calls=(
            ToolCall(id="c1", name="get_dpd", arguments={"loan_id": "L-1"}),
            ToolCall(id="c2", name="get_dpd", arguments={"loan_id": "L-2"}),
        ),
    )

    assert to_input([message]) == [
        {"role": "assistant", "content": "Checking both."},
        {"type": "function_call", "call_id": "c1", "name": "get_dpd", "arguments": '{"loan_id": "L-1"}'},
        {"type": "function_call", "call_id": "c2", "name": "get_dpd", "arguments": '{"loan_id": "L-2"}'},
    ]


def test_an_assistant_message_with_no_text_sends_only_the_calls() -> None:
    message = Message(
        role="assistant",
        content="",
        tool_calls=(ToolCall(id="c1", name="get_dpd", arguments={}),),
    )

    assert [item.get("type") for item in to_input([message])] == ["function_call"]


def test_a_tool_message_becomes_function_call_output() -> None:
    message = Message(role="tool", content='{"dpd": 47}', tool_call_id="c1")

    assert to_input([message]) == [
        {"type": "function_call_output", "call_id": "c1", "output": '{"dpd": 47}'}
    ]


def test_a_tool_message_without_a_call_id_is_refused() -> None:
    with pytest.raises(ModelError):
        to_input([Message(role="tool", content="{}")])


# --- the request itself -----------------------------------------------------


def test_every_request_is_stateless() -> None:
    """store=False always.  Nothing about a case is kept on Azure's side."""
    transport = FakeTransport(TURN_2)
    model, _ = build(transport)

    model.complete(HISTORY)

    body = transport.bodies[0]
    assert body["store"] is False
    assert "previous_response_id" not in body
    assert "temperature" not in body


def test_tools_are_sent_strict_and_omitted_when_there_are_none() -> None:
    transport = FakeTransport(TURN_2, TURN_2)
    model, _ = build(transport)

    model.complete(HISTORY, [TOOL])
    model.complete(HISTORY)

    assert transport.bodies[0]["tools"][0]["strict"] is True
    assert "tools" not in transport.bodies[1]


def test_reasoning_effort_and_budget_are_sent() -> None:
    transport = FakeTransport(TURN_2)
    model, _ = build(transport, reasoning_effort="low", max_output_tokens=1234)

    model.complete(HISTORY)

    assert transport.bodies[0]["reasoning"] == {"effort": "low"}
    assert transport.bodies[0]["max_output_tokens"] == 1234


# --- mapping in -------------------------------------------------------------


def test_a_function_call_becomes_a_tool_call_with_parsed_arguments() -> None:
    model, _ = build(FakeTransport(TURN_1))

    reply = model.complete(HISTORY, [TOOL])

    assert reply.text is None
    assert reply.tool_calls == (
        ToolCall(id="call_Kr2uufyB9FIxiliTOkFHbtQu", name="get_dpd", arguments={"loan_id": "L-1001"}),
    )


def test_a_message_becomes_text_with_no_tool_calls() -> None:
    model, _ = build(FakeTransport(TURN_2))

    reply = model.complete(HISTORY)

    assert reply.text == "Days past due (DPD) for loan L-1001 is 47 days."
    assert reply.tool_calls == ()
    assert reply.model == "gpt-5-mini"


def test_usage_counts_reasoning_inside_output() -> None:
    model, _ = build(FakeTransport(TURN_1))

    usage = model.complete(HISTORY).usage

    assert (usage.input_tokens, usage.output_tokens) == (81, 150)


def test_arguments_that_are_not_json_raise_without_echoing_them() -> None:
    """Arguments can carry account ids.  An error message is a log line."""
    broken = json.loads(json.dumps(TURN_1))
    broken["output"][1]["arguments"] = '{"loan_id": "L-1001"'
    model, _ = build(FakeTransport(broken))

    with pytest.raises(ModelError) as caught:
        model.complete(HISTORY)

    assert "L-1001" not in str(caught.value)


# --- failures ---------------------------------------------------------------


def test_a_429_is_retried_and_its_retry_after_is_honoured() -> None:
    transport = FakeTransport(TransportError(429, "slow down", retry_after=2.0), TURN_2)
    model, delays = build(transport)

    reply = model.complete(HISTORY)

    assert reply.text is not None
    assert delays == [2.0]
    assert len(transport.bodies) == 2


def test_backoff_doubles_when_azure_gives_no_retry_after() -> None:
    transport = FakeTransport(TransportError(503, ""), TransportError(503, ""), TURN_2)
    model, delays = build(transport, backoff=1.0)

    model.complete(HISTORY)

    assert delays == [1.0, 2.0]


def test_retries_stop_at_the_limit() -> None:
    transport = FakeTransport(*[TransportError(503, "down") for _ in range(4)])
    model, _ = build(transport, max_retries=3)

    with pytest.raises(ModelError):
        model.complete(HISTORY)

    assert len(transport.bodies) == 4  # the first try plus three retries


def test_a_400_is_never_retried() -> None:
    """Retrying a bad request only burns quota."""
    transport = FakeTransport(TransportError(400, "bad request"))
    model, delays = build(transport)

    with pytest.raises(ModelError):
        model.complete(HISTORY)

    assert len(transport.bodies) == 1
    assert delays == []


def test_a_blocked_prompt_raises_content_blocked() -> None:
    body = '{"error": {"code": "content_filter", "message": "filtered"}}'
    model, _ = build(FakeTransport(TransportError(400, body)))

    with pytest.raises(ContentBlocked):
        model.complete(HISTORY)


def test_a_blocked_completion_raises_content_blocked() -> None:
    blocked = json.loads(json.dumps(TURN_2))
    blocked["content_filters"][1]["blocked"] = True
    model, _ = build(FakeTransport(blocked))

    with pytest.raises(ContentBlocked):
        model.complete(HISTORY)


def test_running_out_of_budget_raises_incomplete() -> None:
    """A reasoning model can think its whole budget away and say nothing.

    That must not look like a normal reply with text=None.
    """
    incomplete = {
        **TURN_1,
        "status": "incomplete",
        "incomplete_details": {"reason": "max_output_tokens"},
    }
    model, _ = build(FakeTransport(incomplete))

    with pytest.raises(ModelIncomplete, match="max_output_tokens"):
        model.complete(HISTORY)


def test_an_incomplete_content_filter_stop_raises_content_blocked() -> None:
    stopped = {**TURN_2, "status": "incomplete", "incomplete_details": {"reason": "content_filter"}}
    model, _ = build(FakeTransport(stopped))

    with pytest.raises(ContentBlocked):
        model.complete(HISTORY)


def test_a_model_without_a_deployment_refuses_to_exist() -> None:
    with pytest.raises(ModelError):
        AzureChatModel(deployment="", transport=FakeTransport())