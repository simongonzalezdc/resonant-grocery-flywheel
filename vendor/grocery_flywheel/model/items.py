"""Single home for item depletion math.

Every panel must agree on how consumed an item is. Before this module
existed, the analysis path and the easy-food path each had their own
consumed-fraction function with different field precedence, so the same
item could show different depletion in different panels. Both paths now
delegate here.

Precedence when several encodings are present:
``remaining_fraction`` (inverse) → ``units_total``/``units_remaining`` →
``consumed_fraction`` (direct). All results are clamped to [0, 1].
"""

from __future__ import annotations

from typing import Any, TypedDict


class Item(TypedDict, total=False):
    """Read-side shape of one item in a state file.

    ``total=False`` documents the lenient reader: only ``name`` is
    required in practice, everything else is optional with defaults.
    Depletion may be expressed in any one of three encodings; see
    :func:`consumed_fraction`.
    """

    name: str
    role: str
    category: str
    storage: str
    spend: float
    remaining_fraction: float | None
    units_total: int | None
    units_remaining: int | None
    consumed_fraction: float | None
    notes: str
    pricing_status: str
    last_price_check: str
    added_on: str


def clamp(value: float) -> float:
    """Clamp to the [0, 1] interval."""
    return max(0.0, min(1.0, value))


def consumed_fraction(item: dict[str, Any]) -> float:
    """Return the best-known consumed fraction for an item.

    Accepts any of the three depletion encodings and always returns a
    float in [0, 1]. Items with no depletion data are 0.0 (not consumed),
    never an error — reading old states stays lenient.
    """
    if item.get("remaining_fraction") is not None:
        return clamp(1.0 - float(item["remaining_fraction"]))

    total = item.get("units_total")
    remaining = item.get("units_remaining")
    if total not in (None, 0) and remaining is not None:
        return clamp((float(total) - float(remaining)) / float(total))

    if item.get("consumed_fraction") is not None:
        return clamp(float(item["consumed_fraction"]))

    return 0.0
