"""Back-compat shim: rendering lives in the ``rendering`` package now.

The historical ``render_*`` helper names still resolve so existing tests
and downstream code keep working; new code should import from
``grocery_flywheel.rendering``.
"""

from __future__ import annotations

from .rendering import render_dashboard


def render_bar(fraction: float) -> str:
    from .rendering.panels import _bar
    return _bar(fraction)


def render_easy_food(summary: dict) -> str:
    from .rendering.panels import _easy_food
    return _easy_food({"easy_food": summary or {}})


def render_visits(summary: dict) -> str:
    from .rendering.panels import _trips
    return _trips({"visits_summary": summary or {}})


def render_pulses(rows: list[dict]) -> str:
    from .rendering.panels import _pulses
    return _pulses({"pulses": rows})


__all__ = [
    "render_dashboard",
    "render_bar",
    "render_easy_food",
    "render_visits",
    "render_pulses",
]
