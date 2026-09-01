"""Ticket 03: every rendered promise is computed by real code.

- hourly_value is actually read from the state (the trip panel used to
  always show $0.00 while telling the user to set a value it never read)
- the sample state carries no dead data
- easy-food ordering is numeric, not lexicographic
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from grocery_flywheel.core import analyze_state
from grocery_flywheel.easy_food import easy_food_summary

REPO_ROOT = Path(__file__).resolve().parent.parent


def _state(**extra):
    base = {
        "as_of": "2026-06-10",
        "order": {"store": "Store", "date": "2026-06-01", "total": 100.0},
        "visits": [
            {"visit_type": "in_store", "started_at": "2026-06-07T10:00",
             "duration_min": 45},
            {"visit_type": "delivery", "started_at": "2026-06-08T10:00",
             "duration_min": 60},
        ],
    }
    base.update(extra)
    return base


def test_hourly_value_is_read_from_state():
    with_value = analyze_state(_state(hourly_value=25))["visits_summary"]
    assert with_value["amortized_cost_total"] == round(105 / 60 * 25, 2)  # 43.75


def test_missing_hourly_value_defaults_to_zero_not_error():
    assert analyze_state(_state())["visits_summary"]["amortized_cost_total"] == 0.0


def test_sample_state_has_no_dead_data_and_wires_hourly_value():
    sample = json.loads((REPO_ROOT / "examples" / "sample_state.json").read_text())
    assert "retailer_profiles" not in sample, "dead key: no code reads it"
    assert "hourly_value" in sample


def test_easy_food_orders_numerically_oldest_first():
    state = {
        "as_of": "2026-06-10",
        "order": {"store": "S", "date": "2026-06-01", "total": 1},
        "items": [
            {"name": "young", "role": "bridge_food", "added_on": "2026-06-09",
             "consumed_fraction": 0.0},
            {"name": "old", "role": "bridge_food", "added_on": "2026-05-31",
             "consumed_fraction": 0.0},
            {"name": "middle", "role": "protein", "added_on": "2026-06-04",
             "consumed_fraction": 0.0},
        ],
    }
    summary = easy_food_summary(state, today=date(2026, 6, 10))
    names = [row["name"] for row in summary["items"]]
    # oldest first: old (10d) → middle (6d) → young (1d).
    # The old lexicographic sort would have put "10d ago" before "1d ago"
    # and "6d ago" last ("10d ago" < "1d ago" < "6d ago" as strings).
    assert names == ["old", "middle", "young"]
