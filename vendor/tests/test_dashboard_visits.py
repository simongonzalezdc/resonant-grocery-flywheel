"""Integration tests for the Easy Food and Trip Overhead panels."""

from __future__ import annotations

import json
from pathlib import Path

from grocery_flywheel.core import analyze_state
from grocery_flywheel.render import render_dashboard

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_shows_easy_food_panel_for_topups():
    state = json.loads((ROOT / "examples" / "sample_state.json").read_text())
    # Add a fresh top-up so the panel has something to surface
    state["items"].append({
        "name": "Example top-up",
        "role": "bridge_food",
        "added_on": "2026-06-05",
        "consumed_fraction": 0.0,
    })
    html = render_dashboard(analyze_state(state))
    assert "Easy Food" in html
    assert "Example top-up" in html


def test_dashboard_shows_trip_overhead_panel_with_visit():
    state = json.loads((ROOT / "examples" / "sample_state.json").read_text())
    state["visits"] = [
        {
            "id": "v-test",
            "visit_type": "in_store",
            "started_at": "2026-06-05T10:00",
            "duration_min": 45,
            "purchases": [],
            "notes": "",
            "created_at": "2026-06-05T10:00",
        },
    ]
    html = render_dashboard(analyze_state(state))
    assert "Trip Overhead" in html
    assert "1" in html
    assert "45" in html
    assert "in_store" in html


def test_dashboard_trip_overhead_handles_no_visits():
    state = {
        "as_of": "2026-06-07",
        "order": {"store": "X", "date": "2026-05-20", "total": 0},
        "items": [],
        "sourcing_research": [],
        "visits": [],
    }
    html = render_dashboard(analyze_state(state))
    assert "Trip Overhead" in html
    assert "No visits recorded yet" in html
