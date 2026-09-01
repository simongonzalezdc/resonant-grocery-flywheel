from __future__ import annotations

from datetime import date
from typing import Any

from .model.contract import CartPlan, SCHEMA_VERSION, to_dict
from .privacy import can_persist_correction_telemetry


DRAFT_EDIT_ACTIONS = {
    "add_item",
    "remove_item",
    "change_quantity",
    "change_source",
    "approve_item",
    "reject_item",
}


def generate_cart_plan(analysis: dict[str, Any], *, mode: str = "pickup") -> dict[str, Any]:
    if mode not in {"pickup", "delivery", "in_person"}:
        raise ValueError("mode must be pickup, delivery, or in_person")

    items = []
    for row in analysis.get("sourcing_research", [])[:5]:
        best = (row.get("alternatives") or [{}])[0]
        items.append(
            {
                "item": row["item"],
                "action": "review_alternate_source" if mode != "in_person" else "check_aisle_price",
                "source": best.get("source", row.get("current_source", "")),
                "reason": row.get("recommendation", ""),
                "approval_state": "needs_human_approval",
            }
        )
    for item in analysis.get("items", []):
        if item.get("consumed_fraction", 0) >= 0.8 and len(items) < 8:
            items.append(
                {
                    "item": item["name"],
                    "action": "restock",
                    "source": "normal store",
                    "reason": "High observed depletion.",
                    "approval_state": "needs_human_approval",
                }
            )
    return to_dict(CartPlan(mode=mode, approval_required=True, items=items))


def generate_run_sheet(analysis: dict[str, Any]) -> dict[str, Any]:
    rows = {}
    for item in generate_cart_plan(analysis, mode="in_person")["items"]:
        rows.setdefault(item["source"], []).append(item)
    return {
        "schema_version": analysis.get("schema_version"),
        "privacy_class": "sensitive_cart_plan",
        "mode": "in_person",
        "checkout_available": False,
        "approval_required": True,
        "sections": rows,
    }


def create_draft_edit_event(
    *,
    item: str,
    action: str,
    consent: dict[str, Any] | None,
    note: str = "",
    source: str = "user_explicit",
    created_at: str | None = None,
) -> dict[str, Any] | None:
    if action not in DRAFT_EDIT_ACTIONS:
        allowed = ", ".join(sorted(DRAFT_EDIT_ACTIONS))
        raise ValueError(f"unknown draft edit action {action!r}; expected one of: {allowed}")
    if not can_persist_correction_telemetry(consent):
        return None
    return {
        "schema_version": SCHEMA_VERSION,
        "privacy_class": "sensitive_correction_telemetry",
        "event_type": "draft_edit",
        "item": item,
        "action": action,
        "note": note,
        "source": source,
        "created_at": created_at or date.today().isoformat(),
        "storage": consent.get("correction_telemetry", "local_only") if consent else "none",
    }


def normalize_draft_edit_event(
    event: dict[str, Any],
    *,
    consent: dict[str, Any] | None,
) -> dict[str, Any]:
    if not can_persist_correction_telemetry(consent):
        raise ValueError("draft_edit_events require local_only or hosted_opt_in correction telemetry consent")
    if not isinstance(event, dict):
        raise ValueError("draft_edit_events entries must be objects")
    if "item" not in event:
        raise ValueError("draft_edit_events entries require item")
    if "action" not in event:
        raise ValueError("draft_edit_events entries require action")
    normalized = create_draft_edit_event(
        item=str(event["item"]),
        action=str(event["action"]),
        consent=consent,
        note=str(event.get("note", "")),
        source=str(event.get("source", "imported_draft_edit")),
        created_at=event.get("created_at"),
    )
    if normalized is None:
        raise ValueError("draft_edit_events could not be normalized without consent")
    return normalized


def normalize_draft_edit_events(
    events: list[dict[str, Any]] | None,
    *,
    consent: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if events is None:
        return []
    if not isinstance(events, list):
        raise ValueError("draft_edit_events must be a list")
    return [normalize_draft_edit_event(event, consent=consent) for event in events]


def record_draft_edit(
    state: dict[str, Any],
    *,
    item: str,
    action: str,
    note: str = "",
) -> dict[str, Any]:
    event = create_draft_edit_event(
        item=item,
        action=action,
        consent=state.get("consent"),
        note=note,
    )
    if event is None:
        return state
    state.setdefault("draft_edit_events", []).append(event)
    return state


def assert_no_checkout_surface(commands: list[str], modules: list[str]) -> list[str]:
    errors = []
    forbidden = ["checkout", "order-submit", "external_cart_draft"]
    for value in commands + modules:
        for token in forbidden:
            if token in value:
                errors.append(f"forbidden external cart surface: {value}")
    return errors
