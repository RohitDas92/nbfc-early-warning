from nbfc_ews.domain.routing import route


def test_no_open_case_opens_one():
    assert route("bounce_pattern", None) == "open"


def test_less_severe_signal_joins():
    assert route("moratorium_ending", "dpd_bucket_movement") == "join"


def test_equal_severity_joins():
    assert route("bounce_pattern", "bounce_pattern") == "join"


def test_more_severe_signal_escalates():
    assert route("dpd_bucket_movement", "moratorium_ending") == "escalate"

def test_every_signal_type_has_a_severity():
    from nbfc_ews.domain.routing import _SEVERITY
    from nbfc_ews.domain.signals import _RULES

    emitted = set()
    for rule in _RULES:
        # the signal_type is baked into each rule, so read it off the source
        emitted.add(rule.__name__.replace("check_", ""))

    missing = emitted - set(_SEVERITY)
    assert not missing, f"no severity for: {sorted(missing)}"