import json
from pathlib import Path

from grocery_flywheel.core import analyze_state, item_consumed_fraction
from grocery_flywheel.mcp_server import handle_message, handle_tool_call
from grocery_flywheel.retailer_adapter import (
    best_import_profiles,
    capability_matrix,
    validate_retailer_profile,
)


ROOT = Path(__file__).resolve().parents[1]


def test_item_consumed_fraction_from_units():
    item = {"units_total": 8, "units_remaining": 2}
    assert item_consumed_fraction(item) == 0.75


def test_item_consumed_fraction_from_remaining_fraction():
    item = {"remaining_fraction": 0.25}
    assert item_consumed_fraction(item) == 0.75


def test_sample_state_produces_runway_and_preference_signal():
    state = json.loads((ROOT / "examples" / "sample_state.json").read_text())
    analysis = analyze_state(state)

    assert analysis["consumed_value"] > 15
    assert analysis["estimated_days_remaining"] is not None
    assert analysis["acquisition_channel"] == "retailer_history_import"
    assert analysis["inventory_surface"]["type"] == "personal_grocery"
    assert any(item["role"] == "critical_household_essential" for item in analysis["items"])
    assert any(row["item"] == "Dish soap" for row in analysis["sourcing_research"])
    assert analysis["dietary_profiles"][0]["profile_id"] == "household-default"
    assert any(pref["key"] == "avoid_diced_chicken" for pref in analysis["preferences"])


def test_substitution_prefers_better_fit_even_when_unit_price_is_tied():
    state = json.loads((ROOT / "examples" / "sample_state.json").read_text())
    analysis = analyze_state(state)

    top = analysis["substitutions"][0]
    assert top["candidate"] == "Tyson grilled strips"
    assert top["fit"] == "better"


def test_retailer_profiles_validate_and_rank_import_paths():
    profiles = json.loads((ROOT / "examples" / "retailer_profiles.json").read_text())

    errors = [error for profile in profiles for error in validate_retailer_profile(profile)]
    assert errors == []

    matrix = capability_matrix(profiles)
    assert matrix[0]["id"] == "generic.browser_retailer"
    assert "purchase_history" in matrix[0]["enabled_capabilities"]

    import_profiles = best_import_profiles(profiles)
    assert [profile["id"] for profile in import_profiles] == [
        "generic.browser_retailer",
        "generic.warehouse_or_online",
    ]


def test_retailer_profile_rejects_order_submission_for_mvp():
    profile = {
        "id": "bad.submitter",
        "name": "Bad Submitter",
        "type": "grocery",
        "channels": ["delivery"],
        "acquisition_methods": ["retailer_history_import"],
        "capabilities": {
            "purchase_history": True,
            "product_search": True,
            "price_lookup": True,
            "unit_price": True,
            "availability": True,
            "substitutions": True,
            "cart_draft": True,
            "order_submit": True,
        },
    }

    assert "order_submit must stay false for MVP adapter profiles" in validate_retailer_profile(profile)


def test_mcp_server_analyzes_sample_state():
    result = handle_tool_call(
        "analyze_replenishment_state",
        {"state_path": str(ROOT / "examples" / "sample_state.json")},
    )

    assert result["acquisition_channel"] == "retailer_history_import"
    assert result["estimated_days_remaining"] is not None


def test_mcp_server_lists_tools():
    response = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert response is not None
    tools = response["result"]["tools"]
    assert any(tool["name"] == "render_replenishment_dashboard" for tool in tools)
