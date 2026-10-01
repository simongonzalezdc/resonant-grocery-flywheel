"""Read-side TypedDicts for the state document and the analysis result.

These types document the lenient reader contract: they carry no runtime
validation (that arrives with the canonical write/import path) and exist
so the implicit dict-key contract scattered across modules has one
authoritative spelling. ``total=False`` marks everything optional —
``analyze_state`` defaults missing pieces rather than rejecting them,
which is what keeps old state files rendering across schema vintages.
"""

from __future__ import annotations

from typing import Any, TypedDict

from .items import Item


class Visit(TypedDict, total=False):
    id: str
    visit_type: str
    started_at: str
    duration_min: int
    purchases: list[dict[str, Any]]
    notes: str
    created_at: str


class Substitution(TypedDict, total=False):
    current: str
    candidate: str
    current_unit_price: float
    candidate_unit_price: float
    fit: str
    read: str


class SourcingAlternative(TypedDict, total=False):
    source: str
    unit_price: float
    savings: str
    constraints: list[str]
    confidence: str
    checked_date: str


class SourcingRow(TypedDict, total=False):
    item: str
    current_source: str
    current_unit_price: float
    research_question: str
    decision_boundary: str
    recommendation: str
    alternatives: list[SourcingAlternative]


class Preference(TypedDict, total=False):
    key: str
    signal: str
    rule: str


class Pulse(TypedDict, total=False):
    date: str
    text: str


class DietaryRestriction(TypedDict, total=False):
    type: str
    value: str
    safety_tier: str
    behavior: str


class DietaryProfile(TypedDict, total=False):
    profile_id: str
    label: str
    restrictions: list[DietaryRestriction]


class Order(TypedDict):
    store: str
    date: str
    total: float


class State(TypedDict, total=False):
    as_of: str
    order: Order
    items: list[Item]
    inventory_surface: dict[str, str]
    acquisition_channel: str
    dietary_profiles: list[DietaryProfile]
    preferences: list[Preference]
    substitutions: list[Substitution]
    sourcing_research: list[SourcingRow]
    pulses: list[Pulse]
    visits: list[Visit]


class Analysis(TypedDict, total=False):
    """The dict returned by ``analyze_state`` — the renderers' contract."""

    order: Order
    as_of: str
    inventory_surface: dict[str, str]
    acquisition_channel: str
    days_elapsed: int
    items: list[dict[str, Any]]
    consumed_value: float
    known_consumed_fraction: float
    estimated_total_days: float | None
    estimated_days_remaining: float | None
    role_summary: list[dict[str, Any]]
    freshness: dict[str, Any]
    easy_food: dict[str, Any]
    visits_summary: dict[str, Any]
    preferences: list[Preference]
    dietary_profiles: list[DietaryProfile]
    substitutions: list[Substitution]
    sourcing_research: list[SourcingRow]
    pulses: list[Pulse]
