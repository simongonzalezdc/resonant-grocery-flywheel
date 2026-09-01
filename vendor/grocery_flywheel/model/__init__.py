"""The model package is the single home for the state contract's domain
math: depletion, dates, and the read-side TypedDicts. Modules and panels
consume these; they must not re-implement them."""

from .items import Item, clamp, consumed_fraction
from .state import (
    Analysis,
    DietaryProfile,
    Order,
    Preference,
    Pulse,
    SourcingRow,
    State,
    Substitution,
    Visit,
)
from .timeutil import age_in_days, parse_day

__all__ = [
    "Analysis",
    "DietaryProfile",
    "Item",
    "Order",
    "Preference",
    "Pulse",
    "SourcingRow",
    "State",
    "Substitution",
    "Visit",
    "age_in_days",
    "clamp",
    "consumed_fraction",
    "parse_day",
]
