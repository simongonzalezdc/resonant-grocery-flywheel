"""Single home for ISO date/datetime parsing and age math.

Freshness badges and easy-food rotation previously each carried their own
date parsing with slightly different tolerance (one accepted only plain
dates, the other also full datetimes). Both delegate here now.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def parse_day(value: Any) -> date | None:
    """Parse a plain ISO date or full ISO datetime string to a date.

    Returns ``None`` for missing, non-string, or unparseable values so
    callers can treat "no signal" uniformly instead of crashing on old
    or hand-edited states.
    """
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None


def age_in_days(checked: Any, *, today: date) -> int | None:
    """Return whole days between ``checked`` and ``today``, or None.

    ``None`` means "no recorded date" — the dashboard renders that as a
    distinct state, not as zero.
    """
    parsed = parse_day(checked)
    if parsed is None:
        return None
    return (today - parsed).days
