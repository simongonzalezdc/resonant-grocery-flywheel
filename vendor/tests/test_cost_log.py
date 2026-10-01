"""Tests for grocery_flywheel.cost_log — visit cost capture.

The flywheel tracks depletion and pricing. To know whether a trip was
worth taking on its own, the user also needs to know how long it took and
what its amortized time cost was. This module keeps a structured visit
log alongside the state, with a small summary the dashboard can render.
"""

from __future__ import annotations

from datetime import date

import pytest

from grocery_flywheel.cost_log import (
    VALID_VISIT_TYPES,
    Visit,
    add_visit,
    amortized_cost,
    parse_visit_type,
    visits_summary,
)


def test_parse_visit_type_known_values():
    assert parse_visit_type("in_store") == "in_store"
    assert parse_visit_type("pickup") == "pickup"
    assert parse_visit_type("delivery") == "delivery"


def test_parse_visit_type_normalizes_case():
    assert parse_visit_type("IN_STORE") == "in_store"
    assert parse_visit_type("Pickup") == "pickup"


def test_parse_visit_type_rejects_unknown():
    with pytest.raises(ValueError):
        parse_visit_type("spaceship")


def test_valid_visit_types_is_a_set():
    assert isinstance(VALID_VISIT_TYPES, set)
    assert "in_store" in VALID_VISIT_TYPES
    assert "pickup" in VALID_VISIT_TYPES
    assert "delivery" in VALID_VISIT_TYPES


def test_add_visit_appends_to_state():
    state = {"visits": []}
    v = add_visit(
        state,
        visit_type="in_store",
        started_at="2026-06-07T10:00",
        duration_min=42,
    )
    assert v["visit_type"] == "in_store"
    assert v["duration_min"] == 42
    assert len(state["visits"]) == 1


def test_add_visit_initialises_empty_list():
    state = {}
    add_visit(state, visit_type="pickup", started_at="2026-06-07T11:00", duration_min=15)
    assert state["visits"][0]["visit_type"] == "pickup"


def test_add_visit_assigns_id_and_created_at():
    state = {"visits": []}
    v = add_visit(
        state, visit_type="delivery", started_at="2026-06-07T18:00", duration_min=10,
    )
    assert v["id"].startswith("v-")
    assert v["created_at"]


def test_add_visit_optional_fields_default_to_empty():
    state = {"visits": []}
    v = add_visit(
        state, visit_type="in_store", started_at="2026-06-07T10:00", duration_min=20,
    )
    assert v["purchases"] == []
    assert v["notes"] == ""


def test_amortized_cost_zero_when_no_hourly_value():
    assert amortized_cost(60, hourly_value=0) == 0.0
    assert amortized_cost(60, hourly_value=None) == 0.0


def test_amortized_cost_rates_minutes():
    # $30/hr, 30 min = $15
    assert amortized_cost(30, hourly_value=30) == 15.0
    # $20/hr, 90 min = $30
    assert amortized_cost(90, hourly_value=20) == 30.0


def test_amortized_cost_rounds_to_cents():
    # $25/hr, 7 min = $2.9166... -> $2.92
    assert amortized_cost(7, hourly_value=25) == 2.92


def test_visits_summary_empty():
    summary = visits_summary({"visits": []})
    assert summary["visit_count"] == 0
    assert summary["total_minutes"] == 0
    assert summary["by_type"] == {}
    assert summary["amortized_cost_total"] == 0.0


def test_visits_summary_aggregates():
    state = {
        "visits": [
            {"visit_type": "in_store", "duration_min": 45, "started_at": "2026-06-01T10:00"},
            {"visit_type": "in_store", "duration_min": 30, "started_at": "2026-06-04T11:00"},
            {"visit_type": "pickup", "duration_min": 10, "started_at": "2026-06-06T18:00"},
        ]
    }
    summary = visits_summary(state, hourly_value=24)
    assert summary["visit_count"] == 3
    assert summary["total_minutes"] == 85
    assert summary["by_type"]["in_store"] == 2
    assert summary["by_type"]["pickup"] == 1
    assert summary["by_type_minutes"]["in_store"] == 75
    # 85 min @ $24/hr = $34
    assert summary["amortized_cost_total"] == 34.0


def test_visits_summary_window_filters_by_date():
    today = date(2026, 6, 7)
    state = {
        "visits": [
            {"visit_type": "in_store", "duration_min": 60, "started_at": "2026-05-01T10:00"},
            {"visit_type": "in_store", "duration_min": 30, "started_at": "2026-06-05T10:00"},
        ]
    }
    summary = visits_summary(state, hourly_value=20, window_days=7, today=today)
    # only the 2026-06-05 visit is in the 7-day window ending 2026-06-07
    assert summary["visit_count"] == 1
    assert summary["total_minutes"] == 30


def test_visits_summary_skips_visits_without_started_at():
    state = {
        "visits": [
            {"visit_type": "in_store", "duration_min": 45, "started_at": "2026-06-01T10:00"},
            {"visit_type": "in_store", "duration_min": 30},  # no started_at
        ]
    }
    summary = visits_summary(state, window_days=30, today=date(2026, 6, 7))
    # only one visit is in the window
    assert summary["visit_count"] == 1


def test_visit_dataclass_round_trip():
    """Visit can be constructed and serialised as JSON for state storage."""
    v = Visit(
        id="v-abc",
        visit_type="in_store",
        started_at="2026-06-07T10:00",
        duration_min=42,
        purchases=[],
        notes="",
        created_at="2026-06-07T10:00",
    )
    as_dict = v.to_dict()
    assert as_dict["id"] == "v-abc"
    assert as_dict["duration_min"] == 42
