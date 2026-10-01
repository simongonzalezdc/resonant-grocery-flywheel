"""grocery_flywheel.freshness — small helpers for surfacing data-freshness signals.

The dashboard uses these to show how confident we are in prices and sourcing
research. The point is not to enforce a freshness policy; it is to make the
user notice when data is going stale so they can either refresh it or
downgrade confidence.

This module is generic over the captured-at field. It does not know what an
item is or what its price means. The dashboard passes a callable that knows
how to extract a check date from a given object.

Pricing provenance is already documented in
``docs/adapters.md`` as a
first-class concept. This module adds a presentation layer for it on the
items and sourcing research that the dashboard already renders.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable, Iterable

from .model import age_in_days as _model_age_in_days

# A field older than this is considered stale. The user is the source of
# truth on this number; 7 days is the default but the dashboard could expose
# it later as a setting.
STALE_DAYS = 7

# Known pricing_status values on an item. Unknown values are treated as
# "priced" so the dashboard does not flag a field the user has not set.
KNOWN_PRICING_STATUSES = {"priced", "unpriced", "estimated", "gift"}


def age_in_days(checked: Any, *, today: date) -> int | None:
    """Back-compat shim: date math lives in the model package now.

    Accepts plain dates and full datetimes (the model unifies the two
    tolerances the freshness and easy-food paths used to have).
    """
    return _model_age_in_days(checked, today=today)


def is_stale(age_days: int | None) -> bool:
    """Return True if the data is older than the staleness threshold or has
    no recorded check date at all."""
    if age_days is None:
        return True
    return age_days >= STALE_DAYS


def freshness_badge(age_days: int | None) -> str:
    """Render a short, human-readable freshness label for the dashboard."""
    if age_days is None:
        return "no check date"
    if age_days == 0:
        return "today"
    return f"{age_days}d ago"


def pricing_status_reason(pricing_status: str, age_days: int | None) -> str:
    """Return a one-line explanation of why a row is fresh or stale."""
    if pricing_status == "unpriced":
        return "no price captured"
    if pricing_status == "estimated":
        return "estimated (low confidence)"
    if pricing_status == "gift":
        return "gift (price optional)"
    if is_stale(age_days):
        return "priced but stale"
    return "priced recently"


def item_freshness(
    item: dict[str, Any],
    *,
    today: date,
    check_date_fn: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Return a small dict describing how fresh an item's pricing is.

    ``check_date_fn`` is the hook the caller supplies to extract the captured
    date from an item. The default looks at ``last_price_check`` and falls
    back to ``added_on``. The dashboard can pass a different function if the
    state schema is extended later.
    """
    if check_date_fn is None:
        def _item_check_date(it: dict[str, Any]) -> Any:
            return it.get("last_price_check") or it.get("added_on")
        check_date_fn = _item_check_date

    pricing_status = item.get("pricing_status") or "priced"
    last_check = check_date_fn(item)
    age = age_in_days(last_check, today=today)
    # "estimated" is fresh in time but low in confidence. Treat as stale so
    # the dashboard shows it explicitly until a real check replaces it.
    if pricing_status == "estimated":
        stale = True
    else:
        stale = is_stale(age) or pricing_status == "unpriced"

    return {
        "name": item.get("name", ""),
        "pricing_status": pricing_status,
        "age_label": freshness_badge(age),
        "pricing_stale": stale,
        "reason": pricing_status_reason(pricing_status, age),
    }


def sourcing_freshness(
    row: dict[str, Any],
    *,
    today: date,
    check_date_fn: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Return a small dict describing how fresh a sourcing research row is.

    The default ``check_date_fn`` pulls the first alternative's
    ``checked_date``. If there are no alternatives, the row is treated as
    stale.
    """
    if check_date_fn is None:
        def _row_check_date(r: dict[str, Any]) -> Any:
            alternatives = r.get("alternatives", []) or []
            return alternatives[0].get("checked_date") if alternatives else None
        check_date_fn = _row_check_date

    last_check = check_date_fn(row)
    age = age_in_days(last_check, today=today)
    return {
        "item": row.get("item", ""),
        "age_label": freshness_badge(age),
        "stale": is_stale(age),
    }


def summarize_freshness(
    items: Iterable[dict[str, Any]],
    sourcing_research: Iterable[dict[str, Any]],
    *,
    today: date,
) -> dict[str, Any]:
    """Roll item and sourcing-research freshness up into counts the dashboard
    can show in a single panel."""
    item_rows = [item_freshness(it, today=today) for it in items]
    sourcing_rows = [sourcing_freshness(r, today=today) for r in sourcing_research]

    fresh = sum(1 for r in item_rows if not r["pricing_stale"])
    stale = sum(1 for r in item_rows if r["pricing_stale"])
    stale_sourcing = [r for r in sourcing_rows if r["stale"]]

    return {
        "items": item_rows,
        "sourcing": sourcing_rows,
        "fresh_count": fresh,
        "stale_count": stale,
        "stale_sourcing": stale_sourcing,
    }
