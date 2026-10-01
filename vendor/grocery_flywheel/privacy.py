from __future__ import annotations

from typing import Any


PRIVACY_CLASS_BY_FIELD: dict[str, str] = {
    "purchase_history": "sensitive_purchase_history",
    "order": "sensitive_purchase_history",
    "items": "sensitive_purchase_history",
    "household_inventory": "sensitive_household_inventory",
    "inventory_surface": "sensitive_household_inventory",
    "dietary_profiles": "sensitive_dietary_profile",
    "dietary_evaluations": "sensitive_dietary_profile",
    "corrections": "sensitive_correction_telemetry",
    "correction_events": "sensitive_correction_telemetry",
    "draft_edit_events": "sensitive_correction_telemetry",
    "retailer_session": "sensitive_retailer_session",
    "cart_plan": "sensitive_cart_plan",
    "run_sheet": "sensitive_cart_plan",
}
CORRECTION_TELEMETRY_VALUES = {"local_only", "hosted_opt_in", "disabled", "none"}
RETAILER_SESSION_STORAGE_VALUES = {"none", "session_only", "user_opt_in"}

HOSTED_BETA_REQUIRED_CONTROLS = [
    "export_flow",
    "delete_flow",
    "encryption_at_rest_or_provider_equivalent",
    "retention_criteria",
    "session_clearing",
    "secrets_log_hygiene",
    "no_password_storage",
]


def privacy_class_for(field: str) -> str:
    return PRIVACY_CLASS_BY_FIELD.get(field, "internal_operational")


def privacy_metadata(*fields: str) -> dict[str, str]:
    """Return field -> privacy class metadata for canonical objects."""
    return {field: privacy_class_for(field) for field in fields}


def default_consent() -> dict[str, Any]:
    """Local-first consent defaults for MVP telemetry."""
    return {
        "correction_telemetry": "local_only",
        "hosted_sync": False,
        "retailer_session_storage": "none",
        "password_storage": "forbidden",
    }


def can_persist_correction_telemetry(consent: dict[str, Any] | None) -> bool:
    if not consent:
        return False
    return consent.get("correction_telemetry") in {"local_only", "hosted_opt_in"}


def hosted_beta_gate(status: dict[str, bool] | None = None) -> dict[str, Any]:
    checks = status or {}
    missing = [
        control
        for control in HOSTED_BETA_REQUIRED_CONTROLS
        if not bool(checks.get(control))
    ]
    return {
        "ready": not missing,
        "missing_controls": missing,
        "required_controls": HOSTED_BETA_REQUIRED_CONTROLS,
    }
