"""Tests for grocery_flywheel.freshness."""

from __future__ import annotations

from datetime import date

from grocery_flywheel.freshness import (
    STALE_DAYS,
    age_in_days,
    freshness_badge,
    is_stale,
    item_freshness,
    pricing_status_reason,
    sourcing_freshness,
    summarize_freshness,
)


def test_age_in_days_handles_missing():
    assert age_in_days(None, today=date(2026, 6, 6)) is None
    assert age_in_days("", today=date(2026, 6, 6)) is None
    assert age_in_days("not-a-date", today=date(2026, 6, 6)) is None
    assert age_in_days("2026-06-01", today=date(2026, 6, 6)) == 5
    assert age_in_days("2026-06-06", today=date(2026, 6, 6)) == 0


def test_is_stale_thresholds():
    assert is_stale(0) is False
    assert is_stale(STALE_DAYS - 1) is False
    assert is_stale(STALE_DAYS) is True
    assert is_stale(30) is True
    assert is_stale(None) is True


def test_freshness_badge_text():
    assert freshness_badge(0) == "today"
    assert freshness_badge(3) == "3d ago"
    assert freshness_badge(None) == "no check date"


def test_pricing_status_reason_strings():
    assert pricing_status_reason("priced", 1) == "priced recently"
    assert pricing_status_reason("unpriced", None) == "no price captured"
    assert pricing_status_reason("estimated", 0) == "estimated (low confidence)"
    assert pricing_status_reason("gift", None) == "gift (price optional)"
    assert pricing_status_reason("priced", 30) == "priced but stale"


def test_item_freshness_unpriced_is_stale():
    item = {
        "name": "Example top-up",
        "pricing_status": "unpriced",
        "added_on": "2026-06-01",
    }
    info = item_freshness(item, today=date(2026, 6, 6))
    assert info["pricing_stale"] is True
    assert info["reason"] == "no price captured"
    assert info["age_label"] == "5d ago"


def test_item_freshness_estimated_is_stale_even_if_recent():
    item = {
        "name": "Example estimate",
        "pricing_status": "estimated",
        "last_price_check": "2026-06-06",
    }
    info = item_freshness(item, today=date(2026, 6, 6))
    assert info["pricing_stale"] is True
    assert info["reason"] == "estimated (low confidence)"
    assert info["age_label"] == "today"


def test_item_freshness_priced_recent_is_fresh():
    item = {
        "name": "Example priced",
        "pricing_status": "priced",
        "last_price_check": "2026-06-05",
    }
    info = item_freshness(item, today=date(2026, 6, 6))
    assert info["pricing_stale"] is False
    assert info["reason"] == "priced recently"


def test_item_freshness_falls_back_to_added_on():
    item = {"name": "Example", "added_on": "2026-06-05"}
    info = item_freshness(item, today=date(2026, 6, 6))
    assert info["pricing_stale"] is False
    assert info["age_label"] == "1d ago"


def test_item_freshness_custom_check_date_fn():
    item = {"name": "Example", "custom_field": "2026-05-01"}
    info = item_freshness(
        item, today=date(2026, 6, 6),
        check_date_fn=lambda it: it.get("custom_field"),
    )
    assert info["pricing_stale"] is True
    assert info["age_label"] == "36d ago"


def test_sourcing_freshness_flags_old_research():
    row = {
        "item": "Example item",
        "alternatives": [{"checked_date": "2026-05-20", "unit_price": 0.10}],
    }
    info = sourcing_freshness(row, today=date(2026, 6, 6))
    assert info["stale"] is True
    assert info["age_label"] == "17d ago"


def test_sourcing_freshness_fresh_when_recent():
    row = {
        "item": "Example item",
        "alternatives": [{"checked_date": "2026-06-05", "unit_price": 0.10}],
    }
    info = sourcing_freshness(row, today=date(2026, 6, 6))
    assert info["stale"] is False
    assert info["age_label"] == "1d ago"


def test_sourcing_freshness_no_alternatives_is_stale():
    row = {"item": "Example item", "alternatives": []}
    info = sourcing_freshness(row, today=date(2026, 6, 6))
    assert info["stale"] is True
    assert info["age_label"] == "no check date"


def test_summarize_freshness_counts():
    items = [
        {"name": "A", "pricing_status": "priced", "last_price_check": "2026-06-06"},
        {"name": "B", "pricing_status": "unpriced", "added_on": "2026-06-01"},
        {"name": "C", "pricing_status": "estimated", "last_price_check": "2026-06-06"},
    ]
    sourcing = [
        {"item": "X", "alternatives": [{"checked_date": "2026-06-05"}]},
        {"item": "Y", "alternatives": [{"checked_date": "2026-05-01"}]},
    ]
    summary = summarize_freshness(items, sourcing, today=date(2026, 6, 6))
    assert summary["fresh_count"] == 1
    assert summary["stale_count"] == 2
    assert len(summary["stale_sourcing"]) == 1
    assert summary["stale_sourcing"][0]["item"] == "Y"


def test_summarize_freshness_empty_inputs():
    summary = summarize_freshness([], [], today=date(2026, 6, 6))
    assert summary["fresh_count"] == 0
    assert summary["stale_count"] == 0
    assert summary["stale_sourcing"] == []
