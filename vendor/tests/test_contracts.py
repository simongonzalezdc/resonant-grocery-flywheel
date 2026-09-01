import json
from pathlib import Path

from grocery_flywheel.model.contract import SCHEMA_VERSION, validate_canonical_state
from grocery_flywheel.importers import import_normalized_history
from grocery_flywheel.privacy import hosted_beta_gate


ROOT = Path(__file__).resolve().parents[1]


def test_imported_state_has_schema_privacy_confidence_and_provenance():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    state = import_normalized_history(payload)

    assert state["schema_version"] == SCHEMA_VERSION
    assert state["purchase_history"]["schema_version"] == SCHEMA_VERSION
    assert state["purchase_history"]["privacy_class"] == "sensitive_purchase_history"
    assert state["corrections"][0]["schema_version"] == SCHEMA_VERSION
    assert state["corrections"][0]["privacy_class"] == "sensitive_correction_telemetry"
    assert state["privacy"]["purchase_history"] == "sensitive_purchase_history"
    assert state["consent"]["correction_telemetry"] == "local_only"
    assert state["consent"]["password_storage"] == "forbidden"
    assert validate_canonical_state(state) == []
    assert all(item["schema_version"] == SCHEMA_VERSION for item in state["items"])
    assert all(item["privacy_class"] == "sensitive_purchase_history" for item in state["items"])
    assert any(item["confidence"] == "low" for item in state["items"])
    assert all(item["source_provenance"]["source"] == "retailer_history_import" for item in state["items"])


def test_canonical_state_rejects_non_object_state_and_order():
    assert validate_canonical_state([]) == ["state must be an object"]

    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    state = import_normalized_history(payload)
    state["order"] = False

    assert "order must be an object" in validate_canonical_state(state)


def test_canonical_state_requires_analyze_order_fields_and_as_of():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    state = import_normalized_history(payload)

    state.pop("as_of")
    assert "missing as_of" in validate_canonical_state(state)

    state = import_normalized_history(payload)
    state["as_of"] = False
    assert "as_of must be a string" in validate_canonical_state(state)

    state = import_normalized_history(payload)
    state["as_of"] = "not-a-date"
    assert "as_of must be an ISO date" in validate_canonical_state(state)

    state = import_normalized_history(payload)
    state["as_of"] = "20260526"
    assert "as_of must be an ISO date" in validate_canonical_state(state)

    state = import_normalized_history(payload)
    state["order"].pop("total")
    assert "order missing total" in validate_canonical_state(state)

    state = import_normalized_history(payload)
    state["order"]["store"] = False
    state["order"]["date"] = False
    state["order"]["total"] = False
    errors = validate_canonical_state(state)
    assert "order.store must be a string" in errors
    assert "order.date must be a string" in errors
    assert "order.total must be numeric" in errors

    state = import_normalized_history(payload)
    state["order"]["date"] = "not-a-date"
    assert "order.date must be an ISO date" in validate_canonical_state(state)

    state = import_normalized_history(payload)
    state["order"]["date"] = "2026-W22-2"
    assert "order.date must be an ISO date" in validate_canonical_state(state)


def test_canonical_state_requires_item_analysis_fields():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    state = import_normalized_history(payload)

    state["items"][0].pop("name")
    assert "items[0].name must be a string" in validate_canonical_state(state)

    state = import_normalized_history(payload)
    state["items"][0]["name"] = ""
    assert "items[0].name must be a string" in validate_canonical_state(state)

    state = import_normalized_history(payload)
    state["items"][0].pop("spend")
    assert "items[0] missing spend" in validate_canonical_state(state)

    state = import_normalized_history(payload)
    state["items"][0]["spend"] = False
    state["items"][0]["unit_price"] = "cheap"
    state["items"][0]["remaining_fraction"] = "half"
    errors = validate_canonical_state(state)

    assert "items[0].spend must be numeric" in errors
    assert "items[0].unit_price must be numeric" in errors
    assert "items[0].remaining_fraction must be numeric" in errors


def test_canonical_state_validates_substitution_rows_before_analysis():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    state = import_normalized_history(payload)
    state["substitutions"] = [
        {
            "candidate": "",
            "current_unit_price": {},
            "candidate_unit_price": "cheap",
            "trip_friction": [],
            "candidate_product_evidence": 1,
        }
    ]

    errors = validate_canonical_state(state)

    assert "substitutions[0].current must be a string" in errors
    assert "substitutions[0].candidate must be a string" in errors
    assert "substitutions[0].current_unit_price must be numeric" in errors
    assert "substitutions[0].candidate_unit_price must be numeric" in errors
    assert "substitutions[0].trip_friction must be numeric" in errors
    assert "substitutions[0].candidate_product_evidence must be a list" in errors


def test_canonical_state_validates_sourcing_research_rows_before_analysis():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    state = import_normalized_history(payload)
    state["sourcing_research"] = [
        {
            "alternatives": [
                {
                    "source": 1,
                    "savings_amount": {},
                    "checked_date": "20260526",
                    "constraints": [False],
                }
            ]
        }
    ]

    errors = validate_canonical_state(state)

    assert "sourcing_research[0].item must be a string" in errors
    assert "sourcing_research[0].alternatives[0].source must be a string" in errors
    assert "sourcing_research[0].alternatives[0].savings_amount must be numeric" in errors
    assert "sourcing_research[0].alternatives[0].checked_date must be an ISO date" in errors
    assert "sourcing_research[0].alternatives[0].constraints[0] must be a string" in errors


def test_external_cart_draft_is_rejected_from_canonical_state():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    state = import_normalized_history(payload)
    state["external_cart_draft"] = {"items": []}

    assert "external_cart_draft is excluded from MVP code paths" in validate_canonical_state(state)


def test_product_evidence_requires_type_source_date_and_schema():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    state = import_normalized_history(payload)
    state["items"][0]["product_evidence"] = [
        {
            "source": "package",
            "checked_date": "2026-05-26",
            "ingredients": ["coffee"],
        }
    ]

    errors = validate_canonical_state(state)

    assert "items[0].product_evidence[0] missing evidence_type" in errors
    assert "items[0].product_evidence[0] missing schema_version" in errors


def test_canonical_state_validates_nested_date_fields():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    state = import_normalized_history(payload)
    state["items"][0]["product_evidence"] = [
        {
            "schema_version": SCHEMA_VERSION,
            "evidence_type": "ingredient_label",
            "source": "package",
            "checked_date": "2026-05-26",
        }
    ]
    state["items"][0]["product_evidence"][0]["checked_date"] = "20260526"
    state["corrections"][0]["created_at"] = "2026-W22-2"
    state["draft_edit_events"] = [
        {
            "schema_version": SCHEMA_VERSION,
            "privacy_class": "sensitive_correction_telemetry",
            "event_type": "draft_edit",
            "item": "Coffee",
            "action": "reject_item",
            "created_at": "not-a-date",
        }
    ]
    state["pulses"] = [{"date": "2026-05-26", "text": "Fixture pulse."}]
    state["pulses"][0]["date"] = "20260526"
    state["sourcing_research"] = [
        {
            "item": "Coffee",
            "alternatives": [
                {
                    "source": "Warehouse",
                    "unit_price": 0.5,
                    "checked_date": "2026-W22-2",
                }
            ],
        }
    ]

    errors = validate_canonical_state(state)

    assert "items[0].product_evidence[0].checked_date must be an ISO date" in errors
    assert "corrections[0].created_at must be an ISO date" in errors
    assert "draft_edit_events[0].created_at must be an ISO date" in errors
    assert "pulses[0].date must be an ISO date" in errors
    assert "sourcing_research[0].alternatives[0].checked_date must be an ISO date" in errors


def test_correction_and_draft_events_require_privacy_metadata():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    state = import_normalized_history(payload)
    state["corrections"] = [{"item": "Chicken", "signal": "wrong_format"}]
    state["draft_edit_events"] = [{"event_type": "draft_edit", "item": "Coffee", "action": "reject_item"}]

    errors = validate_canonical_state(state)

    assert "corrections[0] missing schema_version" in errors
    assert "corrections[0] missing sensitive_correction_telemetry privacy_class" in errors
    assert "draft_edit_events[0] missing schema_version" in errors
    assert "draft_edit_events[0] missing sensitive_correction_telemetry privacy_class" in errors


def test_dietary_profiles_require_object_entries_and_restrictions():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    state = import_normalized_history(payload)

    state["dietary_profiles"] = [False]
    assert "dietary_profiles[0] must be an object" in validate_canonical_state(state)

    state["dietary_profiles"] = [{"restrictions": {}}]
    assert "dietary_profiles[0].restrictions must be a list" in validate_canonical_state(state)

    state["dietary_profiles"] = [{"restrictions": None}]
    assert "dietary_profiles[0].restrictions must be a list" in validate_canonical_state(state)

    state["dietary_profiles"] = [{"restrictions": [False]}]
    assert (
        "dietary_profiles[0].restrictions[0] must be an object"
        in validate_canonical_state(state)
    )


def test_adapter_matrix_requires_list_of_objects():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    state = import_normalized_history(payload)

    state["adapter_matrix"] = {"bad": "shape"}
    assert "adapter_matrix must be a list" in validate_canonical_state(state)

    state["adapter_matrix"] = [False]
    assert "adapter_matrix[0] must be an object" in validate_canonical_state(state)


def test_sensitive_event_collections_reject_falsey_non_lists():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    for field_name in ("corrections", "draft_edit_events"):
        for value in ("", 0, False, {}):
            state = import_normalized_history(payload)
            state[field_name] = value

            assert f"{field_name} must be a list" in validate_canonical_state(state)


def test_sensitive_events_require_enabled_correction_telemetry_consent():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    state = import_normalized_history(payload)
    state["consent"]["correction_telemetry"] = "disabled"

    errors = validate_canonical_state(state)

    assert "sensitive correction telemetry requires local_only or hosted_opt_in consent" in errors


def test_empty_consent_object_is_not_defaulted_during_validation():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["corrections"] = []
    state = import_normalized_history(payload)
    state["consent"] = {}

    errors = validate_canonical_state(state)

    assert "consent.correction_telemetry is missing or unsupported" in errors


def test_consent_values_are_validated():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    state = import_normalized_history(payload)
    state["consent"]["correction_telemetry"] = "</script><script>alert(1)</script>"

    assert "consent.correction_telemetry is missing or unsupported" in validate_canonical_state(state)


def test_hosted_beta_gate_requires_privacy_controls():
    gate = hosted_beta_gate({"export_flow": True, "delete_flow": True})

    assert not gate["ready"]
    assert "no_password_storage" in gate["missing_controls"]
    assert "session_clearing" in gate["missing_controls"]
