"""Tests for grocery_flywheel.easy_food — unopened top-up surfacing.

The flywheel knows which items a user bought as a top-up, how much of
each has been consumed, and when the item entered the run. The easy-food
panel surfaces items that are still unopened (or barely used) so the user
can rotate them into meals before they expire or before the next
top-up duplicates the stock.
"""

from __future__ import annotations

from datetime import date

from grocery_flywheel.easy_food import easy_food_summary, render_easy_food


def _state_with_items(items):
    return {
        "as_of": "2026-06-07",
        "items": items,
    }


def test_easy_food_finds_unopened_topups():
    items = [
        {
            "name": "Example top-up",
            "role": "bridge_food",
            "pricing_status": "unpriced",
            "added_on": "2026-06-01",
            "consumed_fraction": 0.0,
        },
        {
            "name": "Example protein",
            "role": "protein",
            "pricing_status": "estimated",
            "added_on": "2026-06-02",
            "consumed_fraction": 0.1,
        },
    ]
    summary = easy_food_summary(_state_with_items(items), today=date(2026, 6, 7))
    assert summary["count"] == 2
    assert {row["name"] for row in summary["items"]} == {"Example top-up", "Example protein"}


def test_easy_food_excludes_baseline_order_items():
    """Items without ``added_on`` are baseline items, not top-ups."""
    items = [
        {
            "name": "Original burritos",
            "role": "bridge_food",
            "consumed_fraction": 0.0,
        },
    ]
    summary = easy_food_summary(_state_with_items(items), today=date(2026, 6, 7))
    assert summary["count"] == 0


def test_easy_food_excludes_consumed_items():
    """Already-eaten top-ups are not rotation candidates."""
    items = [
        {
            "name": "Half-eaten top-up",
            "role": "bridge_food",
            "added_on": "2026-06-01",
            "consumed_fraction": 0.6,
        },
    ]
    summary = easy_food_summary(_state_with_items(items), today=date(2026, 6, 7))
    assert summary["count"] == 0


def test_easy_food_excludes_cooking_lane_roles():
    """Items in cooking roles (pantry_base, flavor_unlock) are not easy food."""
    items = [
        {
            "name": "Rice bag",
            "role": "pantry_base",
            "added_on": "2026-06-01",
            "consumed_fraction": 0.0,
        },
    ]
    summary = easy_food_summary(_state_with_items(items), today=date(2026, 6, 7))
    assert summary["count"] == 0


def test_easy_food_window_excludes_old_topups():
    """Top-ups added more than 30 days ago are out of the easy-food window."""
    items = [
        {
            "name": "Old top-up",
            "role": "bridge_food",
            "added_on": "2026-04-01",
            "consumed_fraction": 0.0,
        },
    ]
    summary = easy_food_summary(_state_with_items(items), today=date(2026, 6, 7))
    assert summary["count"] == 0


def test_easy_food_includes_bridge_food_and_protein_only():
    items = [
        {"name": "A", "role": "bridge_food", "added_on": "2026-06-05", "consumed_fraction": 0.0},
        {"name": "B", "role": "protein", "added_on": "2026-06-05", "consumed_fraction": 0.0},
        {"name": "C", "role": "drink", "added_on": "2026-06-05", "consumed_fraction": 0.0},
        {"name": "D", "role": "coffee", "added_on": "2026-06-05", "consumed_fraction": 0.0},
    ]
    summary = easy_food_summary(_state_with_items(items), today=date(2026, 6, 7))
    assert summary["count"] == 2
    assert {row["name"] for row in summary["items"]} == {"A", "B"}


def test_easy_food_empty_state():
    summary = easy_food_summary(_state_with_items([]), today=date(2026, 6, 7))
    assert summary["count"] == 0
    assert summary["items"] == []


def test_render_easy_food_html_escapes_names():
    summary = {
        "count": 1,
        "items": [
            {"name": "<script>x</script>", "role": "bridge_food", "age_label": "today"},
        ],
    }
    html = render_easy_food(summary)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_easy_food_handles_zero():
    summary = {"count": 0, "items": []}
    html = render_easy_food(summary)
    assert "No unopened top-ups" in html


def test_easy_food_age_label_handles_malformed_added_on():
    """If added_on is set but malformed, fall through the window filter."""
    items = [
        {
            "name": "Bad-date top-up",
            "role": "bridge_food",
            "added_on": "not-a-date",
            "consumed_fraction": 0.0,
        },
    ]
    summary = easy_food_summary(_state_with_items(items), today=date(2026, 6, 7))
    # _age_days returns None for malformed dates, which is filtered out
    assert summary["count"] == 0


def test_easy_food_uses_units_remaining_when_consumed_fraction_missing():
    """If consumed_fraction is missing but units_remaining == units_total, treat as unopened."""
    items = [
        {
            "name": "Sealed top-up",
            "role": "protein",
            "added_on": "2026-06-05",
            "units_total": 4,
            "units_remaining": 4,
        },
    ]
    summary = easy_food_summary(_state_with_items(items), today=date(2026, 6, 7))
    assert summary["count"] == 1
