import pytest

from nbfc_ews.llm.base import Message
from nbfc_ews.llm.fake import FakeChatModel, ScriptExhausted, calls_tool, says

ASK = [Message(role="user", content="what is happening with this account?")]


def script():
    return [
        calls_tool("get_payment_behaviour", account_id="EDU0000001"),
        says("repayment is deteriorating"),
    ]


def test_replies_come_back_in_script_order():
    model = FakeChatModel(script())

    first = model.complete(ASK)
    second = model.complete(ASK)

    assert first.tool_calls[0].name == "get_payment_behaviour"
    assert first.text is None
    assert second.text == "repayment is deteriorating"
    assert second.tool_calls == ()


def test_two_models_on_the_same_script_agree():
    a = FakeChatModel(script())
    b = FakeChatModel(script())

    assert a.complete(ASK) == b.complete(ASK)
    assert a.complete(ASK) == b.complete(ASK)


def test_running_past_the_script_raises():
    model = FakeChatModel([says("done")])
    model.complete(ASK)

    with pytest.raises(ScriptExhausted, match="script has 1 replies"):
        model.complete(ASK)


def test_every_reply_reports_usage():
    model = FakeChatModel(script())

    for _ in range(2):
        reply = model.complete(ASK)
        assert reply.usage.input_tokens > 0
        assert reply.usage.output_tokens >= 0


def test_what_was_sent_is_recorded():
    model = FakeChatModel(script())
    model.complete(ASK)

    assert model.calls == [ASK]