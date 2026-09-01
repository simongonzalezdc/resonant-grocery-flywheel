"""The model package is the single home for depletion and date math.

These tests pin the coherence property the redesign bought us: the same
physical depletion expressed in any of the three encodings yields the
same number, everywhere.
"""

from __future__ import annotations

from datetime import date

from grocery_flywheel.core import item_consumed_fraction
from grocery_flywheel.easy_food import _consumed_fraction
from grocery_flywheel.model import clamp, consumed_fraction


def _today() -> date:
    return date(2026, 8, 14)


def test_same_depletion_all_encodings_agree():
    by_remaining = {"remaining_fraction": 0.7}
    by_units = {"units_total": 10, "units_remaining": 7}
    by_consumed = {"consumed_fraction": 0.3}
    values = [
        consumed_fraction(by_remaining),
        consumed_fraction(by_units),
        consumed_fraction(by_consumed),
        item_consumed_fraction(by_remaining),
        item_consumed_fraction(by_units),
        item_consumed_fraction(by_consumed),
        _consumed_fraction(by_remaining),
        _consumed_fraction(by_units),
        _consumed_fraction(by_consumed),
    ]
    # 1.0 - 0.7 is 0.2999...98 in binary floating point, as it always was;
    # coherence is about agreement, not bit-exact decimal equality.
    assert all(round(v, 9) == 0.3 for v in values)


def test_precedence_remaining_fraction_beats_units_beats_consumed():
    all_three = {
        "remaining_fraction": 0.5,       # → consumed 0.5 (wins)
        "units_total": 10, "units_remaining": 9,  # → 0.1 (ignored)
        "consumed_fraction": 0.9,        # (ignored)
    }
    units_and_consumed = {
        "units_total": 10, "units_remaining": 9,  # → 0.1 (wins over below)
        "consumed_fraction": 0.9,
    }
    assert consumed_fraction(all_three) == 0.5
    assert consumed_fraction(units_and_consumed) == 0.1


def test_missing_depletion_is_zero_not_error():
    assert consumed_fraction({"name": "thing"}) == 0.0


def test_clamp_bounds():
    assert clamp(-0.5) == 0.0
    assert clamp(1.5) == 1.0
    assert clamp(0.25) == 0.25


def test_negative_and_oversized_inputs_clamped():
    assert consumed_fraction({"consumed_fraction": 1.7}) == 1.0
    assert consumed_fraction({"remaining_fraction": -0.2}) == 1.0


def test_parse_accepts_date_and_datetime():
    from grocery_flywheel.model import age_in_days

    assert age_in_days("2026-08-07", today=_today()) == 7
    assert age_in_days("2026-08-07T10:00:00", today=_today()) == 7
    assert age_in_days("not-a-date", today=_today()) is None
    assert age_in_days(None, today=_today()) is None
    assert age_in_days("", today=_today()) is None
