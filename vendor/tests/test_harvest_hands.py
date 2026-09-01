"""Ticket 07 acceptance: registry architecture, dark command-center,
structural approval boundary, consent-gated correction capture."""

from __future__ import annotations

import json
from pathlib import Path

from grocery_flywheel.core import analyze_state
from grocery_flywheel.draft import generate_cart_plan
from grocery_flywheel.importers import import_normalized_history
from grocery_flywheel.mcp_server import handle_tool_call
from grocery_flywheel.rendering import PANELS, render_dashboard

REPO_ROOT = Path(__file__).resolve().parent.parent


def _legacy():
    return json.loads((REPO_ROOT / "examples" / "sample_state.json").read_text())


def _canonical():
    payload = json.loads(
        (REPO_ROOT / "examples" / "imports" / "example-history.json").read_text()
    )
    return import_normalized_history(payload)


def test_registry_is_ordered_callables_not_a_framework():
    assert isinstance(PANELS, list)
    names = [p["name"] for p in PANELS]
    assert len(names) == len(set(names))
    # D1 order: first-wow leads, corrections capture near the end
    assert names[0] == "first_wow"
    assert names.index("dietary") < names.index("freshness")
    assert "corrections_capture" in names and names[-1] == "pulses"
    for panel in PANELS:
        assert callable(panel["render"])
        assert panel["span"] in {"span-4", "span-6", "span-12"}


def test_every_panel_renders_for_both_state_families():
    for state in (_legacy(), _canonical()):
        analysis = analyze_state(state)
        html = render_dashboard(analysis)
        assert html.startswith("<!doctype html>")
        assert html.count("class='panel") + html.count('class="panel') >= 10
    # dark command-center theme present
    assert "color-scheme: dark" in render_dashboard(analyze_state(_legacy()))


def test_approval_boundary_is_structural():
    analysis = analyze_state(_canonical())
    plan = analysis["cart_plan"]
    assert plan["checkout_available"] is False
    assert plan["approval_required"] is True
    assert all(i["approval_state"] == "needs_human_approval" for i in plan["items"])
    run_sheet = analysis["run_sheet"]
    assert run_sheet["checkout_available"] is False
    assert generate_cart_plan({}, mode="pickup")["checkout_available"] is False


def test_correction_capture_only_renders_under_consent():
    legacy_html = render_dashboard(analyze_state(_legacy()))
    canonical_html = render_dashboard(analyze_state(_canonical()))
    assert "Correction Capture" not in legacy_html      # no consent → no capture UI
    assert "Correction Capture" in canonical_html       # local_only consent → UI present
    assert "Download JSONL" in canonical_html
    assert "never_again" in canonical_html


def test_evidence_drawer_only_for_items_with_evidence():
    canonical_html = render_dashboard(analyze_state(_canonical()))
    assert "<details>" in canonical_html
    legacy_html = render_dashboard(analyze_state(_legacy()))
    assert legacy_html.count("<details>") == 0


def test_pulses_tolerate_note_field():
    state = _legacy()
    state["pulses"] = [{"date": "2026-06-05", "note": "hand-edited pulse"}]
    html = render_dashboard(analyze_state(state))
    assert "hand-edited pulse" in html  # mac-mini fix: row['text'] → .get(text, note)


def test_first_wow_cards_render():
    html = render_dashboard(analyze_state(_canonical()))
    assert "First Look" in html
    assert "Best Sourcing Move" in html
    assert "Potential Unit Savings" in html


def test_mcp_plan_next_cart_asserts_boundary():
    state = _canonical()
    result = handle_tool_call("plan_next_cart", {
        "state_json": json.dumps(state), "mode": "in_person",
    })
    assert result["checkout_available"] is False
    assert result["approval_required"] is True
    assert result["item_count"] >= 0


def test_mcp_tools_list_now_has_five_tools():
    from grocery_flywheel.mcp_server import handle_message
    reply = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tools = {t["name"] for t in reply["result"]["tools"]}
    assert tools == {
        "analyze_replenishment_state",
        "render_replenishment_dashboard",
        "summarize_sourcing_research",
        "evaluate_dietary",
        "plan_next_cart",
    }
