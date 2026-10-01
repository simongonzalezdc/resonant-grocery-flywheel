from grocery_flywheel.corrections import (
    SIGNAL_RULES,
    create_correction_event,
    derived_preferences,
    normalize_correction_events,
    persistable_corrections,
    record_correction,
)


def test_correction_signals_are_distinct_durable_preferences():
    keys = set()
    for signal in SIGNAL_RULES:
        event = create_correction_event("Chicken", signal)
        assert event["signal"] == signal
        keys.add(derived_preferences({"consent": {"correction_telemetry": "local_only"}, "corrections": [event]})[0]["key"])

    assert len(keys) == len(SIGNAL_RULES)


def test_corrections_do_not_persist_without_explicit_local_or_hosted_consent():
    state = {"corrections": [{"item": "Chicken", "signal": "wrong_format"}]}

    assert persistable_corrections(state) == []


def test_imported_corrections_normalize_to_private_schema_events():
    event = normalize_correction_events([{"item": "Chicken", "signal": "wrong_format"}])[0]

    assert event["schema_version"]
    assert event["privacy_class"] == "sensitive_correction_telemetry"


def test_record_correction_is_consent_gated():
    denied = {"consent": {"correction_telemetry": "disabled"}}
    allowed = {"consent": {"correction_telemetry": "local_only"}}

    assert "corrections" not in record_correction(denied, item="Chicken", signal="wrong_format")
    assert record_correction(allowed, item="Chicken", signal="wrong_format")["corrections"][0]["signal"] == "wrong_format"
