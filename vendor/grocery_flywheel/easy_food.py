"""grocery_flywheel.easy_food — surface unopened top-ups before they expire.

The flywheel knows which items the user bought as a top-up, how much of
each has been consumed, and when the item entered the run. The easy-food
panel surfaces items that are still unopened (or barely used) so the
user can rotate them into meals before the next top-up duplicates the
stock, or before a perishable goes past its window.

The matching rules are intentionally narrow:

- Item role must be ``bridge_food`` or ``protein`` (cooking-lane
  items are not easy food and are out of scope here).
- Item must not be a baseline order item — we identify baseline items
  by the absence of an ``added_on`` field, or by ``source == "baseline"``
  when the state records one.
- Consumed fraction must be 0.0 (or ``units_remaining == units_total``).
- ``added_on`` must be within the last 30 days. Beyond that, the
  item is no longer a fresh top-up.

This is the visible surface of two Meta Patterns:
- Pattern 4 (Friction Budget): the user benefits from noticing
  low-friction food before it duplicates effort.
- Pattern 6 (Bridge Inventory): immediate food is the bridge between
  full cooking days; an unopened bridge is wasted runway.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .model import age_in_days, consumed_fraction

EASY_FOOD_ROLES = {"bridge_food", "protein"}
EASY_FOOD_WINDOW_DAYS = 30
EASY_FOOD_MAX_CONSUMED = 0.10  # treat anything <= 10% as effectively unopened


def _age_days(added_on: Any, today: date) -> int | None:
    """Back-compat shim: age math lives in the model package now."""
    return age_in_days(added_on, today=today)


def _consumed_fraction(item: dict[str, Any]) -> float:
    """Back-compat shim: depletion math lives in the model package now.

    The model's precedence treats ``remaining_fraction`` as the strongest
    signal, so a top-up recorded as mostly depleted via remaining_fraction
    correctly fails this panel's unopened filter.
    """
    return consumed_fraction(item)


def _is_baseline(item: dict[str, Any]) -> bool:
    """Baseline items came in on the original order, not as a top-up.

    The signal is the presence of ``added_on``: a top-up is any item with
    a recorded entry date. Baseline items do not have one. This is
    deliberately a presence test, not a value test, so a user can store
    whatever string they want in ``source`` (e.g. ``store baseline``) and
    the easy-food matcher still works.
    """
    return "added_on" not in item


def easy_food_summary(
    state: dict[str, Any],
    *,
    today: date,
    window_days: int = EASY_FOOD_WINDOW_DAYS,
) -> dict[str, Any]:
    """Return a small dict describing the unopened top-ups in the run.

    The dict has ``count`` and ``items`` (each with name, role, age_label).
    Used by the dashboard to render a rotation panel.
    """
    rows: list[dict[str, Any]] = []
    for item in state.get("items", []):
        role = item.get("role")
        if role not in EASY_FOOD_ROLES:
            continue
        if _is_baseline(item):
            continue
        if _consumed_fraction(item) > EASY_FOOD_MAX_CONSUMED:
            continue
        age = _age_days(item.get("added_on"), today)
        if age is None or age > window_days:
            continue
        rows.append({
            "name": item.get("name", ""),
            "role": role,
            "age_days": age,
            "age_label": "today" if age == 0 else f"{age}d ago",
        })
    # Oldest first: the oldest top-up is the closest to leaving the window
    # (and to expiring), so it is the most urgent to rotate. Sorting on the
    # numeric age — the old sort on the label string ordered "10d ago"
    # before "2d ago" lexicographically.
    rows.sort(key=lambda r: r["age_days"], reverse=True)
    return {"count": len(rows), "items": rows}


def render_easy_food(summary: dict[str, Any]) -> str:
    """Back-compat shim — the HTML lives in the rendering package now."""
    from .rendering.panels import _easy_food
    return _easy_food({"easy_food": summary or {}})
