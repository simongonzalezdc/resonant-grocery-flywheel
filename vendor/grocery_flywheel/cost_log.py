"""grocery_flywheel.cost_log — small visit cost capture for the dashboard.

The flywheel tracks depletion and pricing. To know whether a trip was
worth taking on its own, the user also needs to know how long it took
and what its amortized time cost was at a configurable hourly value.
This module keeps a structured visit log alongside the state.

The model is intentionally minimal:

- Each visit has a type (``in_store``, ``pickup``, ``delivery``), a
  ``started_at`` ISO timestamp, and a ``duration_min``.
- Optional ``purchases`` list maps to items that entered the run during
  the visit. The user is the source of truth on what got bought where.
- Optional ``notes`` field is free text.
- ``amortized_cost`` is a derived number: ``duration_min / 60 *
  hourly_value``. The dashboard lets the user set their own hourly value
  or leave it at zero to disable.

This is the visible surface of the friction concept from
``docs/patterns.md`` pattern 4 (Friction Budget): "A cheaper item can lose if it
requires too much cooking, prep, storage, cleanup, or coordination." A
visit log lets the user notice when a trip is becoming a hidden cost.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any

from .model import parse_day

VALID_VISIT_TYPES = {"in_store", "pickup", "delivery"}


def parse_visit_type(value: str) -> str:
    """Normalize a user-typed visit type string to a known canonical form."""
    if not value:
        raise ValueError("visit_type is required")
    normalised = value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalised not in VALID_VISIT_TYPES:
        raise ValueError(
            f"unknown visit_type {value!r}; expected one of {sorted(VALID_VISIT_TYPES)}"
        )
    return normalised


@dataclass
class Visit:
    """One trip to a store or one delivery received."""

    id: str
    visit_type: str
    started_at: str
    duration_min: int
    purchases: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def add_visit(
    state: dict[str, Any],
    *,
    visit_type: str,
    started_at: str,
    duration_min: int,
    purchases: list[dict[str, Any]] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Append a new visit to ``state['visits']`` and return the visit dict.

    The state is mutated in place. A new id and created_at are assigned
    automatically. ``purchases`` defaults to an empty list.
    """
    canonical_type = parse_visit_type(visit_type)
    if not isinstance(started_at, str) or not started_at.strip():
        raise ValueError("started_at is required and must be a non-empty ISO timestamp")
    try:
        datetime.fromisoformat(started_at)
    except ValueError as exc:
        raise ValueError(
            f"started_at must be an ISO timestamp (e.g. 2026-06-07T10:00): {started_at!r}"
        ) from exc
    if isinstance(duration_min, bool) or not isinstance(duration_min, (int, float)):
        raise ValueError("duration_min must be a non-negative integer")
    if float(duration_min) != int(duration_min):
        raise ValueError(f"duration_min must be whole minutes, got {duration_min!r}")
    if int(duration_min) < 0:
        raise ValueError("duration_min must be a non-negative integer")
    visit = Visit(
        id=f"v-{uuid.uuid4().hex[:8]}",
        visit_type=canonical_type,
        started_at=started_at,
        duration_min=int(duration_min),
        purchases=list(purchases or []),
        notes=notes,
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    state.setdefault("visits", []).append(visit.to_dict())
    return visit.to_dict()


def amortized_cost(duration_min: int, *, hourly_value: float | None) -> float:
    """Return the time cost of a visit in dollars.

    A zero or ``None`` hourly value disables the calculation and returns
    0.0. This is the default so the dashboard does not assume a value the
    user has not opted into.
    """
    if not hourly_value or hourly_value <= 0:
        return 0.0
    return round(duration_min / 60.0 * float(hourly_value), 2)


def _within_window(visit: dict[str, Any], *, today: date, window_days: int) -> bool:
    started_at = visit.get("started_at")
    if not started_at:
        return False
    visit_date = parse_day(started_at)
    if visit_date is None:
        return False
    delta = (today - visit_date).days
    return 0 <= delta <= window_days


def _safe_duration(value: Any) -> int:
    """Coerce a visit's duration to whole minutes without crashing.

    Hand-edited states can carry garbage ("abc", None). The lenient read
    path counts the visit but contributes 0 minutes rather than taking
    the whole analysis down (QA finding).
    """
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def visits_summary(
    state: dict[str, Any],
    *,
    hourly_value: float | None = None,
    window_days: int | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Aggregate the visits list into a small dict the dashboard can render.

    Counts and minutes are filtered by an optional rolling window
    (``window_days`` ending at ``today``). The amortized cost total is
    computed from the filtered set.
    """
    visits = state.get("visits", []) or []
    if window_days is not None:
        if today is None:
            today = date.today()
        visits = [v for v in visits if _within_window(v, today=today, window_days=window_days)]

    by_type: dict[str, int] = {}
    by_type_minutes: dict[str, int] = {}
    total_minutes = 0
    for v in visits:
        vt = v.get("visit_type", "unknown")
        dur = _safe_duration(v.get("duration_min", 0))
        by_type[vt] = by_type.get(vt, 0) + 1
        by_type_minutes[vt] = by_type_minutes.get(vt, 0) + dur
        total_minutes += dur

    return {
        "visit_count": len(visits),
        "total_minutes": total_minutes,
        "by_type": by_type,
        "by_type_minutes": by_type_minutes,
        "amortized_cost_total": amortized_cost(total_minutes, hourly_value=hourly_value),
    }
