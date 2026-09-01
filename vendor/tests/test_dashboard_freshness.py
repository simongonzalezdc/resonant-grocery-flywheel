"""Test that the dashboard surfaces a Data Freshness panel."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from grocery_flywheel.core import analyze_state
from grocery_flywheel.render import render_dashboard

ROOT = Path(__file__).resolve().parents[1]


def _mutate_state(state: dict) -> dict:
    """Add pricing_status and last_price_check to demonstrate freshness."""
    today = date.fromisoformat(state["as_of"])
    for item in state["items"]:
        # Most items in the public sample have no captured check date.
        if item.get("name", "").startswith("Bean"):
            item["pricing_status"] = "priced"
            item["last_price_check"] = (today - timedelta(days=1)).isoformat()
        elif item.get("name", "").startswith("Extra firm tofu"):
            item["pricing_status"] = "unpriced"
            item["added_on"] = (today - timedelta(days=10)).isoformat()
    # Mark one sourcing research row stale.
    for row in state.get("sourcing_research", []):
        for alt in row.get("alternatives", []):
            alt["checked_date"] = (today - timedelta(days=30)).isoformat()
    return state


def test_dashboard_surfaces_freshness_panel():
    state = json.loads((ROOT / "examples" / "sample_state.json").read_text())
    state = _mutate_state(state)
    html = render_dashboard(analyze_state(state))
    assert "Data Freshness" in html
    assert "priced recently" in html
    assert "unpriced" in html
    assert "Stale sourcing research" in html


def test_dashboard_freshness_panel_handles_empty_state():
    html = render_dashboard(analyze_state({
        "as_of": "2026-06-06",
        "order": {"store": "X", "date": "2026-05-20", "total": 0},
        "items": [],
        "sourcing_research": [],
    }))
    assert "Data Freshness" in html
    assert "0 priced recently" in html
