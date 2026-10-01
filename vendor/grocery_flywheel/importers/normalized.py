from __future__ import annotations

from datetime import date
from typing import Any

from ..model.contract import canonical_state, is_iso_date
from ..corrections import normalize_correction_events_for_import
from ..draft import normalize_draft_edit_events
from ..normalization import normalize_item
from ..privacy import default_consent


def import_consent(payload: dict[str, Any]) -> dict[str, Any]:
    if "consent" not in payload or payload["consent"] is None:
        return default_consent()
    if not isinstance(payload["consent"], dict):
        raise ValueError("consent must be an object")
    return payload["consent"]


def import_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if "items" not in payload or payload["items"] is None:
        return []
    if not isinstance(payload["items"], list):
        raise ValueError("items must be a list")
    for index, item in enumerate(payload["items"]):
        validate_import_item(item, index=index)
    return payload["items"]


def import_object(payload: dict[str, Any], field: str) -> dict[str, Any]:
    value = payload.get(field)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def import_list(payload: dict[str, Any], field: str) -> list[Any]:
    value = payload.get(field)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def import_dietary_profiles(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = import_list(payload, "dietary_profiles")
    profiles: list[dict[str, Any]] = []
    for index, profile in enumerate(rows):
        if not isinstance(profile, dict):
            raise ValueError(f"dietary_profiles[{index}] must be an object")
        restrictions = profile.get("restrictions", [])
        if not isinstance(restrictions, list):
            raise ValueError(f"dietary_profiles[{index}].restrictions must be a list")
        for restriction_index, restriction in enumerate(restrictions):
            if not isinstance(restriction, dict):
                raise ValueError(
                    f"dietary_profiles[{index}].restrictions[{restriction_index}] must be an object"
                )
        profiles.append(profile)
    return profiles


def validate_import_item(item: Any, *, index: int) -> None:
    if not isinstance(item, dict):
        raise ValueError("items entries must be objects")
    if not str(item.get("name", "")).strip():
        raise ValueError(f"items[{index}] missing name")
    for field in ("quantity", "spend", "total_price", "unit_price"):
        if field in item and item[field] not in (None, ""):
            try:
                float(item[field])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"items[{index}].{field} must be numeric") from exc
    evidence_rows = item.get("product_evidence")
    if evidence_rows is None:
        return
    if not isinstance(evidence_rows, list):
        raise ValueError(f"items[{index}].product_evidence must be a list")
    for evidence_index, evidence in enumerate(evidence_rows):
        if not isinstance(evidence, dict):
            raise ValueError(
                f"items[{index}].product_evidence[{evidence_index}] must be an object"
            )
        for field in ("evidence_type", "source", "checked_date"):
            if not evidence.get(field) or not isinstance(evidence[field], str):
                raise ValueError(
                    f"items[{index}].product_evidence[{evidence_index}] missing {field}"
                )
        if not is_iso_date(evidence["checked_date"]):
            raise ValueError(
                f"items[{index}].product_evidence[{evidence_index}].checked_date must be an ISO date"
            )
        for field in ("ingredients", "allergen_statements", "certifications"):
            if field in evidence and not isinstance(evidence[field], list):
                raise ValueError(
                    f"items[{index}].product_evidence[{evidence_index}].{field} must be a list"
                )
        if "nutrition_facts" in evidence and not isinstance(evidence["nutrition_facts"], dict):
            raise ValueError(
                f"items[{index}].product_evidence[{evidence_index}].nutrition_facts must be an object"
            )


def import_normalized_history(
    payload: dict[str, Any],
    *,
    profile_id: str | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("normalized import payload must be an object")
    order = import_object(payload, "order")
    items = import_items(payload)
    normalized_items = [
        normalize_item(item, source=payload.get("source", "normalized_json"))
        for item in items
    ]
    if "total" not in order:
        order["total"] = round(sum(float(item["spend"]) for item in normalized_items), 2)
    order.setdefault("store", payload.get("store", "Imported retailer"))
    order.setdefault("date", payload.get("date", date.today().isoformat()))

    consent = import_consent(payload)
    extra = {
        "purchase_history": {
            "source": payload.get("source", "normalized_json"),
            "imported_at": as_of or payload.get("as_of") or date.today().isoformat(),
            "confidence": "high",
        },
        "preferences": import_list(payload, "preferences"),
        "corrections": normalize_correction_events_for_import(
            payload.get("corrections", []),
            consent=consent,
        ),
        "draft_edit_events": normalize_draft_edit_events(
            payload.get("draft_edit_events", []),
            consent=consent,
        ),
        "pulses": import_list(payload, "pulses"),
    }
    return canonical_state(
        as_of=as_of or payload.get("as_of") or date.today().isoformat(),
        order=order,
        items=normalized_items,
        acquisition_channel=payload.get("acquisition_channel", "retailer_history_import"),
        inventory_surface=import_object(payload, "inventory_surface")
        if "inventory_surface" in payload
        else None,
        retailer_profiles=[profile_id] if profile_id else import_list(payload, "retailer_profiles"),
        dietary_profiles=import_dietary_profiles(payload),
        consent=consent,
        extra=extra,
    )
