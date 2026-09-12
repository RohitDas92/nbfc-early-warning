from nbfc_ews.domain.signals import Signal
from nbfc_ews.engine.route import route_signals


def _sig(account_id, signal_type):
    return Signal(account_id=account_id, signal_type=signal_type, detail="")


def test_three_signals_on_one_account_open_once():
    signals = [
        _sig("A1", "dpd_bucket_movement"),   # severity 10 -> opens
        _sig("A1", "moratorium_ending"),     # severity  1 -> joins
        _sig("A1", "adverse_event"),         # severity 11 -> escalates
    ]

    actions = route_signals(signals, {})

    assert [a.decision for a in actions] == ["open", "join", "escalate"]
    assert actions[2].case_type == "adverse_event"

def test_existing_case_less_severe_signal_joins():
    actions = route_signals(
        [_sig("A1", "moratorium_ending")],
        {"A1": "bounce_pattern"},
    )

    assert actions[0].decision == "join"
    assert actions[0].case_type == "bounce_pattern"      # unchanged


def test_empty_batch_returns_empty():
    assert route_signals([], {}) == []


def test_caller_dict_is_not_modified():
    existing = {"A1": "moratorium_ending"}

    route_signals([_sig("A1", "adverse_event")], existing)

    assert existing == {"A1": "moratorium_ending"}