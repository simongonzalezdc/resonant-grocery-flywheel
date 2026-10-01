import json
from pathlib import Path
from typing import Any

import pytest

from grocery_flywheel.importers import import_csv_history, import_normalized_history
from grocery_flywheel.normalization import parse_size


ROOT = Path(__file__).resolve().parents[1]


def test_normalized_import_computes_unit_prices_and_keeps_missing_evidence_explicit():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    state = import_normalized_history(payload)

    coffee = next(item for item in state["items"] if item["name"] == "Cafe Bustelo bricks")
    mystery = next(item for item in state["items"] if item["name"] == "Mystery frozen meal")

    assert coffee["unit_price"] == 0.692
    assert coffee["size"]["unit"] == "oz"
    assert mystery["unit_price"] is None
    assert mystery["confidence"] == "low"
    assert mystery["product_evidence"] == []


def test_normalized_import_rejects_non_object_payload():
    payload: Any = []
    with pytest.raises(ValueError, match="normalized import payload must be an object"):
        import_normalized_history(payload)


def test_normalized_import_rejects_malformed_items_container():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["items"] = 0

    with pytest.raises(ValueError, match="items must be a list"):
        import_normalized_history(payload)


def test_normalized_import_rejects_malformed_top_level_containers():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["order"] = []
    with pytest.raises(ValueError, match="order must be an object"):
        import_normalized_history(payload)

    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["preferences"] = {}
    with pytest.raises(ValueError, match="preferences must be a list"):
        import_normalized_history(payload)


def test_normalized_import_rejects_malformed_dietary_profiles():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["dietary_profiles"] = [False]
    with pytest.raises(ValueError, match=r"dietary_profiles\[0\] must be an object"):
        import_normalized_history(payload)

    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["dietary_profiles"] = [{"restrictions": {}}]
    with pytest.raises(ValueError, match=r"dietary_profiles\[0\]\.restrictions must be a list"):
        import_normalized_history(payload)

    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["dietary_profiles"] = [{"restrictions": None}]
    with pytest.raises(ValueError, match=r"dietary_profiles\[0\]\.restrictions must be a list"):
        import_normalized_history(payload)

    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["dietary_profiles"] = [{"restrictions": [False]}]
    with pytest.raises(
        ValueError,
        match=r"dietary_profiles\[0\]\.restrictions\[0\] must be an object",
    ):
        import_normalized_history(payload)


def test_normalized_import_rejects_non_object_item_entries():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["items"] = ["bad item"]

    with pytest.raises(ValueError, match="items entries must be objects"):
        import_normalized_history(payload)


def test_normalized_import_rejects_missing_item_name():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["items"] = [{"spend": 1}]

    with pytest.raises(ValueError, match=r"items\[0\] missing name"):
        import_normalized_history(payload)


def test_normalized_import_rejects_invalid_numeric_item_fields():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["items"] = [{"name": "Coffee", "spend": "not money"}]

    with pytest.raises(ValueError, match=r"items\[0\]\.spend must be numeric"):
        import_normalized_history(payload)


def test_normalized_import_rejects_malformed_product_evidence():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["items"] = [{"name": "Coffee", "spend": 1, "product_evidence": "bad"}]

    with pytest.raises(ValueError, match=r"items\[0\]\.product_evidence must be a list"):
        import_normalized_history(payload)


def test_normalized_import_rejects_malformed_product_evidence_rows_and_fields():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["items"] = [{"name": "Coffee", "spend": 1, "product_evidence": ["bad"]}]
    with pytest.raises(ValueError, match=r"items\[0\]\.product_evidence\[0\] must be an object"):
        import_normalized_history(payload)

    payload["items"] = [
            {
                "name": "Coffee",
                "spend": 1,
                "product_evidence": [
                    {
                        "evidence_type": "ingredient_label",
                        "source": "package",
                        "checked_date": "2026-05-26",
                        "ingredients": "coffee",
                    }
                ],
            }
        ]
    with pytest.raises(
        ValueError,
        match=r"items\[0\]\.product_evidence\[0\]\.ingredients must be a list",
    ):
        import_normalized_history(payload)


def test_normalized_import_rejects_product_evidence_missing_required_metadata():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["items"] = [
        {
            "name": "Coffee",
            "spend": 1,
            "product_evidence": [
                {
                    "source": "package",
                    "checked_date": "2026-05-26",
                    "ingredients": ["coffee"],
                }
            ],
        }
    ]

    with pytest.raises(
        ValueError,
        match=r"items\[0\]\.product_evidence\[0\] missing evidence_type",
    ):
        import_normalized_history(payload)


def test_normalized_import_rejects_product_evidence_non_canonical_dates():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["items"] = [
        {
            "name": "Coffee",
            "spend": 1,
            "product_evidence": [
                {
                    "evidence_type": "ingredient_label",
                    "source": "package",
                    "checked_date": "20260526",
                    "ingredients": ["coffee"],
                }
            ],
        }
    ]

    with pytest.raises(
        ValueError,
        match=r"items\[0\]\.product_evidence\[0\]\.checked_date must be an ISO date",
    ):
        import_normalized_history(payload)


def test_csv_import_produces_canonical_state():
    state = import_csv_history(ROOT / "examples" / "imports" / "example-history.csv")

    assert state["purchase_history"]["source"] == "csv_export"
    assert state["order"]["store"] == "Example Grocery"
    assert len(state["items"]) == 4
    assert any(item["name"] == "Dish soap" for item in state["items"])


def test_normalized_import_keeps_valid_draft_edit_events_private():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["draft_edit_events"] = [
        {
            "item": "Cafe Bustelo bricks",
            "action": "change_quantity",
            "note": "Two bricks lasted longer.",
        }
    ]

    state = import_normalized_history(payload)
    event = state["draft_edit_events"][0]

    assert event["schema_version"]
    assert event["privacy_class"] == "sensitive_correction_telemetry"
    assert event["action"] == "change_quantity"
    assert event["storage"] == "local_only"


def test_normalized_import_rejects_malformed_draft_edit_events():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["draft_edit_events"] = [{"item": "Cafe Bustelo bricks"}]

    with pytest.raises(ValueError, match="draft_edit_events entries require action"):
        import_normalized_history(payload)


def test_normalized_import_rejects_falsey_non_list_draft_edit_events():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["draft_edit_events"] = ""

    with pytest.raises(ValueError, match="draft_edit_events must be a list"):
        import_normalized_history(payload)


def test_normalized_import_rejects_non_object_draft_edit_events():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["draft_edit_events"] = ["bad event"]

    with pytest.raises(ValueError, match="draft_edit_events entries must be objects"):
        import_normalized_history(payload)


def test_normalized_import_rejects_malformed_corrections():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["corrections"] = ["bad event"]

    with pytest.raises(ValueError, match="corrections entries must be objects"):
        import_normalized_history(payload)


def test_normalized_import_rejects_non_list_corrections():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["corrections"] = ""

    with pytest.raises(ValueError, match="corrections must be a list"):
        import_normalized_history(payload)


def test_normalized_import_rejects_corrections_when_consent_disabled():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["consent"] = {
        "correction_telemetry": "disabled",
        "hosted_sync": False,
        "retailer_session_storage": "none",
        "password_storage": "forbidden",
    }

    with pytest.raises(ValueError, match="corrections require local_only or hosted_opt_in"):
        import_normalized_history(payload)


def test_normalized_import_rejects_malformed_falsey_consent_with_corrections():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    payload["consent"] = False

    with pytest.raises(ValueError, match="consent must be an object"):
        import_normalized_history(payload)


def test_size_parser_handles_common_units_and_unknowns():
    assert parse_size("20 lb")["unit"] == "lb"
    assert parse_size("28 fl oz")["unit"] == "fl_oz"
    assert parse_size("6 ct")["amount"] == 6
    assert parse_size("mystery size")["confidence"] == "low"
