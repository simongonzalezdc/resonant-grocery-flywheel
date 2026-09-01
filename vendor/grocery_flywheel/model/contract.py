"""Write-side canonical state contract (harvested from the 2026-05-26 WIP).

This is the fail-closed half of the state contract: importers and writers
produce canonical states stamped with SCHEMA_VERSION and validated by
``validate_canonical_state``. Reading stays lenient (see model.state) so
older, unversioned states keep rendering; the merge with the main lineage
keeps the freshness fields (pricing_status, last_price_check, added_on)
that the WIP had dropped, and preserves added_on presence semantics:
absence means baseline item, so normalization must omit the key rather
than write nulls.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

from ..privacy import (
    CORRECTION_TELEMETRY_VALUES,
    RETAILER_SESSION_STORAGE_VALUES,
    can_persist_correction_telemetry,
    default_consent,
    privacy_metadata,
)


SCHEMA_VERSION = "2026-08-14.mvp2"
ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


@dataclass(frozen=True)
class ProductEvidence:
    evidence_type: str
    source: str
    checked_date: str
    ingredients: list[str] = field(default_factory=list)
    allergen_statements: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    nutrition_facts: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class ProductIdentity:
    name: str
    canonical_name: str
    category: str = "unknown"
    size: dict[str, Any] = field(default_factory=dict)
    confidence: str = "medium"
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class OrderItem:
    name: str
    spend: float
    quantity: float = 1
    category: str = "unknown"
    role: str = "unknown"
    size: dict[str, Any] = field(default_factory=dict)
    unit_price: float | None = None
    pricing_status: str | None = None
    last_price_check: str | None = None
    added_on: str | None = None
    confidence: str = "medium"
    source_provenance: dict[str, Any] = field(default_factory=dict)
    product_evidence: list[dict[str, Any]] = field(default_factory=list)
    privacy_class: str = "sensitive_purchase_history"
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class RetailerProfile:
    id: str
    name: str
    type: str
    channels: list[str]
    acquisition_methods: list[str]
    capabilities: dict[str, bool]
    region: str = "custom"
    constraints: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class SourcingCandidate:
    item: str
    current_source: str
    current_unit_price: float
    alternatives: list[dict[str, Any]]
    recommendation: str
    confidence: str = "medium"
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class DietaryEvaluation:
    item: str
    profile_id: str
    restriction: str
    result: str
    safety_tier: str
    evidence_status: str
    reason: str
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class CorrectionEvent:
    item: str
    signal: str
    note: str = ""
    source: str = "user_explicit"
    created_at: str = field(default_factory=lambda: date.today().isoformat())
    privacy_class: str = "sensitive_correction_telemetry"
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class CartPlan:
    mode: str
    approval_required: bool
    items: list[dict[str, Any]]
    checkout_available: bool = False
    privacy_class: str = "sensitive_cart_plan"
    schema_version: str = SCHEMA_VERSION


def to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, dict):
        return ensure_schema_version(value)
    raise TypeError(f"unsupported contract object: {type(value)!r}")


def ensure_schema_version(value: dict[str, Any]) -> dict[str, Any]:
    if "schema_version" in value:
        return value
    return {"schema_version": SCHEMA_VERSION, **value}


def canonical_state(
    *,
    as_of: str,
    order: dict[str, Any],
    items: list[dict[str, Any]],
    acquisition_channel: str,
    inventory_surface: dict[str, Any] | None = None,
    retailer_profiles: list[str] | None = None,
    dietary_profiles: list[dict[str, Any]] | None = None,
    consent: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "as_of": as_of,
        "inventory_surface": inventory_surface
        or {"type": "personal_grocery", "label": "Home groceries"},
        "acquisition_channel": acquisition_channel,
        "retailer_profiles": retailer_profiles or [],
        "dietary_profiles": dietary_profiles or [],
        "consent": consent if consent is not None else default_consent(),
        "privacy": privacy_metadata(
            "purchase_history",
            "household_inventory",
            "dietary_profiles",
            "dietary_evaluations",
            "corrections",
            "draft_edit_events",
            "retailer_session",
            "cart_plan",
            "run_sheet",
        ),
        "order": ensure_schema_version(order),
        "items": [ensure_schema_version(item) for item in items],
    }
    if extra:
        extra = dict(extra)
        if isinstance(extra.get("purchase_history"), dict):
            extra["purchase_history"] = ensure_schema_version(
                {
                    "privacy_class": "sensitive_purchase_history",
                    **extra["purchase_history"],
                }
            )
        state.update(extra)
    return state


def validate_canonical_state(state: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(state, dict):
        return ["state must be an object"]
    if state.get("schema_version") != SCHEMA_VERSION:
        errors.append("state schema_version is missing or unsupported")
    if "as_of" not in state:
        errors.append("missing as_of")
    elif not isinstance(state["as_of"], str):
        errors.append("as_of must be a string")
    elif not is_iso_date(state["as_of"]):
        errors.append("as_of must be an ISO date")
    if "order" not in state:
        errors.append("missing order")
    elif not isinstance(state["order"], dict):
        errors.append("order must be an object")
    else:
        if state["order"].get("schema_version") != SCHEMA_VERSION:
            errors.append("order missing schema_version")
        for field in ("store", "date", "total"):
            if field not in state["order"]:
                errors.append(f"order missing {field}")
        for field in ("store", "date"):
            if field in state["order"] and not isinstance(state["order"][field], str):
                errors.append(f"order.{field} must be a string")
        if "date" in state["order"] and isinstance(state["order"]["date"], str):
            if not is_iso_date(state["order"]["date"]):
                errors.append("order.date must be an ISO date")
        if "total" in state["order"] and not is_number(state["order"]["total"]):
            errors.append("order.total must be numeric")
    purchase_history = state.get("purchase_history")
    if isinstance(purchase_history, dict):
        if purchase_history.get("schema_version") != SCHEMA_VERSION:
            errors.append("purchase_history missing schema_version")
        if purchase_history.get("privacy_class") != "sensitive_purchase_history":
            errors.append("purchase_history missing sensitive privacy_class")
    privacy = state.get("privacy", {})
    if not isinstance(privacy, dict):
        errors.append("privacy must be an object")
        privacy = {}
    if privacy.get("purchase_history") != "sensitive_purchase_history":
        errors.append("privacy metadata missing purchase_history class")
    items = state.get("items")
    if not isinstance(items, list):
        errors.append("items must be a list")
        items = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"items[{index}] must be an object")
            continue
        errors.extend(validate_item_row(item, index=index))
        if item.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"items[{index}] missing schema_version")
        if "privacy_class" not in item:
            errors.append(f"items[{index}] missing privacy_class")
        if "confidence" not in item:
            errors.append(f"items[{index}] missing confidence")
        errors.extend(
            validate_product_evidence_rows(
                item.get("product_evidence", []),
                prefix=f"items[{index}].product_evidence",
            )
        )
    dietary_profiles = state.get("dietary_profiles", [])
    if not isinstance(dietary_profiles, list):
        errors.append("dietary_profiles must be a list")
    else:
        for index, profile in enumerate(dietary_profiles):
            if not isinstance(profile, dict):
                errors.append(f"dietary_profiles[{index}] must be an object")
                continue
            restrictions = profile.get("restrictions", [])
            if not isinstance(restrictions, list):
                errors.append(f"dietary_profiles[{index}].restrictions must be a list")
                continue
            for restriction_index, restriction in enumerate(restrictions):
                if not isinstance(restriction, dict):
                    errors.append(
                        f"dietary_profiles[{index}].restrictions[{restriction_index}] must be an object"
                    )
    substitutions = state.get("substitutions", [])
    if substitutions is not None:
        if not isinstance(substitutions, list):
            errors.append("substitutions must be a list")
        else:
            for index, row in enumerate(substitutions):
                if not isinstance(row, dict):
                    errors.append(f"substitutions[{index}] must be an object")
                    continue
                errors.extend(validate_substitution_row(row, index=index))
    sourcing_research = state.get("sourcing_research", [])
    if sourcing_research is not None:
        if not isinstance(sourcing_research, list):
            errors.append("sourcing_research must be a list")
        else:
            for index, row in enumerate(sourcing_research):
                if not isinstance(row, dict):
                    errors.append(f"sourcing_research[{index}] must be an object")
                    continue
                errors.extend(validate_sourcing_research_row(row, index=index))
    pulses = state.get("pulses", [])
    if pulses is not None:
        if not isinstance(pulses, list):
            errors.append("pulses must be a list")
        else:
            for index, pulse in enumerate(pulses):
                if not isinstance(pulse, dict):
                    errors.append(f"pulses[{index}] must be an object")
                    continue
                if not pulse.get("date"):
                    errors.append(f"pulses[{index}] missing date")
                elif not isinstance(pulse["date"], str):
                    errors.append(f"pulses[{index}].date must be a string")
                elif not is_iso_date(pulse["date"]):
                    errors.append(f"pulses[{index}].date must be an ISO date")
    adapter_matrix = state.get("adapter_matrix")
    if adapter_matrix is not None:
        if not isinstance(adapter_matrix, list):
            errors.append("adapter_matrix must be a list")
        else:
            for index, row in enumerate(adapter_matrix):
                if not isinstance(row, dict):
                    errors.append(f"adapter_matrix[{index}] must be an object")
    errors.extend(validate_visits(state.get("visits")))
    retailer_profiles = state.get("retailer_profiles")
    if retailer_profiles is not None:
        if not isinstance(retailer_profiles, list):
            errors.append("retailer_profiles must be a list of profile ids")
        else:
            for index, entry in enumerate(retailer_profiles):
                if not isinstance(entry, str) or not entry:
                    errors.append(f"retailer_profiles[{index}] must be a non-empty string")
    hourly_value = state.get("hourly_value")
    if hourly_value is not None:
        if not is_number(hourly_value):
            errors.append("hourly_value must be numeric")
        elif float(hourly_value) < 0:
            errors.append("hourly_value must be non-negative")
    for field_name in ("storage", "preferences_config"):
        value = state.get(field_name)
        if value is not None and not isinstance(value, dict):
            errors.append(f"{field_name} must be an object")
    for error in validate_sensitive_events(
        state.get("corrections", []),
        field_name="corrections",
        privacy_class="sensitive_correction_telemetry",
        required_fields=("item", "signal", "created_at"),
    ):
        errors.append(error)
    for error in validate_sensitive_events(
        state.get("draft_edit_events", []),
        field_name="draft_edit_events",
        privacy_class="sensitive_correction_telemetry",
        required_fields=("event_type", "item", "action", "created_at"),
    ):
        errors.append(error)
    for field_name, privacy_class in (
        ("cart_plan", "sensitive_cart_plan"),
        ("run_sheet", "sensitive_cart_plan"),
    ):
        value = state.get(field_name)
        if value is not None and isinstance(value, dict):
            if value.get("schema_version") != SCHEMA_VERSION:
                errors.append(f"{field_name} missing schema_version")
            if value.get("privacy_class") != privacy_class:
                errors.append(f"{field_name} missing {privacy_class} privacy_class")
        elif value is not None:
            errors.append(f"{field_name} must be an object")
    consent = state.get("consent")
    if not isinstance(consent, dict):
        errors.append("consent must be an object")
        consent = {}
    if consent.get("password_storage") != "forbidden":
        errors.append("password storage must be forbidden")
    if consent.get("correction_telemetry") not in CORRECTION_TELEMETRY_VALUES:
        errors.append("consent.correction_telemetry is missing or unsupported")
    if consent.get("retailer_session_storage") not in RETAILER_SESSION_STORAGE_VALUES:
        errors.append("consent.retailer_session_storage is missing or unsupported")
    if not isinstance(consent.get("hosted_sync"), bool):
        errors.append("consent.hosted_sync must be a boolean")
    sensitive_events_present = bool(state.get("corrections")) or bool(
        state.get("draft_edit_events")
    )
    if sensitive_events_present and not can_persist_correction_telemetry(consent):
        errors.append(
            "sensitive correction telemetry requires local_only or hosted_opt_in consent"
        )
    if "external_cart_draft" in state:
        errors.append("external_cart_draft is excluded from MVP code paths")
    return errors


def validate_item_row(item: dict[str, Any], *, index: int) -> list[str]:
    errors: list[str] = []
    name = item.get("name")
    if not isinstance(name, str) or not name:
        errors.append(f"items[{index}].name must be a string")
    if "spend" not in item:
        errors.append(f"items[{index}] missing spend")
    elif not is_number(item["spend"]):
        errors.append(f"items[{index}].spend must be numeric")
    elif float(item["spend"]) < 0:
        errors.append(f"items[{index}].spend must be non-negative")
    for field_name in (
        "quantity",
        "unit_price",
        "units_total",
        "units_remaining",
        "remaining_fraction",
        "consumed_fraction",
    ):
        if item.get(field_name) is not None and not is_number(item[field_name]):
            errors.append(f"items[{index}].{field_name} must be numeric")
    for field_name in ("quantity", "unit_price"):
        value = item.get(field_name)
        if is_number(value) and float(value) < 0:
            errors.append(f"items[{index}].{field_name} must be non-negative")
    for field_name in ("remaining_fraction", "consumed_fraction"):
        value = item.get(field_name)
        if is_number(value) and not 0.0 <= float(value) <= 1.0:
            errors.append(f"items[{index}].{field_name} must be within [0, 1]")
    total_units = item.get("units_total")
    remaining_units = item.get("units_remaining")
    if (
        is_number(total_units) and is_number(remaining_units)
        and float(remaining_units) > float(total_units)
    ):
        errors.append(
            f"items[{index}].units_remaining cannot exceed units_total"
        )
    # Freshness fields merged from the main lineage. ``added_on`` stays a
    # presence signal (absence = baseline item), so it must be omitted —
    # not set to null — on baseline items; a present-but-null key fails
    # loudly here instead of silently passing.
    if item.get("pricing_status") is not None and not isinstance(item["pricing_status"], str):
        errors.append(f"items[{index}].pricing_status must be a string")
    if "added_on" in item and item["added_on"] is None:
        errors.append(
            f"items[{index}].added_on must be omitted on baseline items, not null "
            "(presence is the top-up signal)"
        )
    for field_name in ("last_price_check", "added_on"):
        value = item.get(field_name)
        if value is not None:
            if not isinstance(value, str):
                errors.append(f"items[{index}].{field_name} must be a string")
            elif not is_iso_date(value):
                errors.append(f"items[{index}].{field_name} must be an ISO date")
    return errors


def validate_substitution_row(row: dict[str, Any], *, index: int) -> list[str]:
    errors: list[str] = []
    for field_name in ("current", "candidate"):
        value = row.get(field_name)
        if not isinstance(value, str) or not value:
            errors.append(f"substitutions[{index}].{field_name} must be a string")
    for field_name in ("current_unit_price", "candidate_unit_price"):
        if field_name not in row:
            errors.append(f"substitutions[{index}] missing {field_name}")
        elif not is_number(row[field_name]):
            errors.append(f"substitutions[{index}].{field_name} must be numeric")
    for field_name in (
        "trip_friction",
        "quality_score",
        "decision_friction",
        "savings_amount",
        "savings_pct",
    ):
        if row.get(field_name) is not None and not is_number(row[field_name]):
            errors.append(f"substitutions[{index}].{field_name} must be numeric")
    for field_name in ("candidate_product_evidence", "product_evidence"):
        if row.get(field_name) is not None:
            errors.extend(
                validate_product_evidence_rows(
                    row[field_name],
                    prefix=f"substitutions[{index}].{field_name}",
                )
            )
    return errors


def validate_sourcing_research_row(row: dict[str, Any], *, index: int) -> list[str]:
    errors: list[str] = []
    item = row.get("item")
    if not isinstance(item, str) or not item:
        errors.append(f"sourcing_research[{index}].item must be a string")
    for field_name in ("current_source", "recommendation", "confidence"):
        if row.get(field_name) is not None and not isinstance(row[field_name], str):
            errors.append(f"sourcing_research[{index}].{field_name} must be a string")
    if row.get("current_unit_price") is not None and not is_number(row["current_unit_price"]):
        errors.append(f"sourcing_research[{index}].current_unit_price must be numeric")

    alternatives = row.get("alternatives", [])
    if not isinstance(alternatives, list):
        errors.append(f"sourcing_research[{index}].alternatives must be a list")
        return errors
    for alternative_index, alternative in enumerate(alternatives):
        prefix = f"sourcing_research[{index}].alternatives[{alternative_index}]"
        if not isinstance(alternative, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for field_name in ("source", "savings", "confidence", "checked_date"):
            if alternative.get(field_name) is not None and not isinstance(
                alternative[field_name], str
            ):
                errors.append(f"{prefix}.{field_name} must be a string")
        checked_date = alternative.get("checked_date")
        if isinstance(checked_date, str) and not is_iso_date(checked_date):
            errors.append(f"{prefix}.checked_date must be an ISO date")
        for field_name in (
            "unit_price",
            "savings_amount",
            "savings_pct",
            "trip_friction",
            "quality_score",
            "decision_friction",
        ):
            if alternative.get(field_name) is not None and not is_number(alternative[field_name]):
                errors.append(f"{prefix}.{field_name} must be numeric")
        constraints = alternative.get("constraints", [])
        if not isinstance(constraints, list):
            errors.append(f"{prefix}.constraints must be a list")
        else:
            for constraint_index, constraint in enumerate(constraints):
                if not isinstance(constraint, str):
                    errors.append(f"{prefix}.constraints[{constraint_index}] must be a string")
    return errors


def validate_product_evidence_rows(rows: Any, *, prefix: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(rows, list):
        return [f"{prefix} must be a list"]
    for evidence_index, evidence in enumerate(rows):
        if not isinstance(evidence, dict):
            errors.append(f"{prefix}[{evidence_index}] must be an object")
            continue
        for evidence_field in ("evidence_type", "source", "checked_date"):
            if not evidence.get(evidence_field):
                errors.append(f"{prefix}[{evidence_index}] missing {evidence_field}")
        checked_date = evidence.get("checked_date")
        if isinstance(checked_date, str) and not is_iso_date(checked_date):
            errors.append(f"{prefix}[{evidence_index}].checked_date must be an ISO date")
        if evidence.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"{prefix}[{evidence_index}] missing schema_version")
    return errors


def validate_visits(visits: Any) -> list[str]:
    """Visits were previously unvalidated; broken rows only surfaced as
    panel crashes. Keep the bar modest: shape, ISO timestamp, sane
    duration (QA hardening 2026-08-16)."""
    if visits is None:
        return []
    if not isinstance(visits, list):
        return ["visits must be a list"]
    errors: list[str] = []
    for index, visit in enumerate(visits):
        if not isinstance(visit, dict):
            errors.append(f"visits[{index}] must be an object")
            continue
        visit_type = visit.get("visit_type")
        if visit_type is not None and not isinstance(visit_type, str):
            errors.append(f"visits[{index}].visit_type must be a string")
        started_at = visit.get("started_at")
        if started_at is not None:
            if not isinstance(started_at, str):
                errors.append(f"visits[{index}].started_at must be a string")
            else:
                try:
                    datetime.fromisoformat(started_at)
                except ValueError:
                    errors.append(
                        f"visits[{index}].started_at must be an ISO timestamp"
                    )
        duration = visit.get("duration_min")
        if duration is not None:
            if not is_number(duration):
                errors.append(f"visits[{index}].duration_min must be numeric")
            elif float(duration) < 0:
                errors.append(f"visits[{index}].duration_min must be non-negative")
    return errors


def validate_sensitive_events(
    rows: Any,
    *,
    field_name: str,
    privacy_class: str,
    required_fields: tuple[str, ...],
) -> list[str]:
    errors: list[str] = []
    if rows is None:
        return errors
    if not isinstance(rows, list):
        return [f"{field_name} must be a list"]
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"{field_name}[{index}] must be an object")
            continue
        if row.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"{field_name}[{index}] missing schema_version")
        if row.get("privacy_class") != privacy_class:
            errors.append(f"{field_name}[{index}] missing {privacy_class} privacy_class")
        for required in required_fields:
            if not row.get(required):
                errors.append(f"{field_name}[{index}] missing {required}")
        created_at = row.get("created_at")
        if isinstance(created_at, str) and not is_iso_date(created_at):
            errors.append(f"{field_name}[{index}].created_at must be an ISO date")
    return errors


def is_number(value: Any) -> bool:
    # NaN and infinities are floats, and Python's json.loads accepts the
    # bare literals — but they are not valid JSON numbers downstream
    # (json.dumps would emit non-strict JSON) and they poison arithmetic.
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    return math.isfinite(value)


def is_iso_date(value: str) -> bool:
    if not ISO_DATE_RE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True
