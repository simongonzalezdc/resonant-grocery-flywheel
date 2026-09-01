from __future__ import annotations

from datetime import date
from typing import Any

from .model.contract import CorrectionEvent, to_dict
from .privacy import can_persist_correction_telemetry


SIGNAL_RULES = {
    "never_again": "Suppress this item and close substitutes unless user manually restores it.",
    "buy_elsewhere": "Prefer alternate retailer sourcing for this item.",
    "wrong_format": "Avoid the same form factor; preserve the broader protein/category need.",
    "too_expensive": "Down-rank unless unit price improves materially.",
    "dietary_conflict": "Treat as safety/preference conflict before savings.",
    "good_default": "Keep as a low-friction default when budget allows.",
    "emergency_only": "Use only as bridge food or stockout fallback.",
}


def create_correction_event(
    item: str,
    signal: str,
    note: str = "",
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    if signal not in SIGNAL_RULES:
        allowed = ", ".join(sorted(SIGNAL_RULES))
        raise ValueError(f"unknown correction signal {signal!r}; expected one of: {allowed}")
    return to_dict(
        CorrectionEvent(
            item=item,
            signal=signal,
            note=note,
            created_at=created_at or date.today().isoformat(),
        )
    )


def normalize_correction_event(event: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ValueError("corrections entries must be objects")
    if "item" not in event:
        raise ValueError("corrections entries require item")
    if "signal" not in event:
        raise ValueError("corrections entries require signal")
    normalized = create_correction_event(
        item=str(event["item"]),
        signal=str(event["signal"]),
        note=str(event.get("note", "")),
        created_at=event.get("created_at"),
    )
    if event.get("source"):
        normalized["source"] = str(event["source"])
    return normalized


def normalize_correction_events(events: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if events is None:
        return []
    if not isinstance(events, list):
        raise ValueError("corrections must be a list")
    return [normalize_correction_event(event) for event in events]


def normalize_correction_events_for_import(
    events: list[dict[str, Any]] | None,
    *,
    consent: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    normalized = normalize_correction_events(events)
    if normalized and not can_persist_correction_telemetry(consent):
        raise ValueError(
            "corrections require local_only or hosted_opt_in correction telemetry consent"
        )
    return normalized


def correction_to_preference(event: dict[str, Any]) -> dict[str, Any]:
    signal = event["signal"]
    return {
        "key": f"{signal}:{event['item'].lower()}",
        "signal": signal,
        "item": event["item"],
        "rule": SIGNAL_RULES[signal],
        "source": "explicit_correction",
        "created_at": event.get("created_at", date.today().isoformat()),
    }


def persistable_corrections(state: dict[str, Any]) -> list[dict[str, Any]]:
    if not can_persist_correction_telemetry(state.get("consent")):
        return []
    return normalize_correction_events(state.get("corrections", []))


def record_correction(
    state: dict[str, Any],
    *,
    item: str,
    signal: str,
    note: str = "",
) -> dict[str, Any]:
    if not can_persist_correction_telemetry(state.get("consent")):
        return state
    state.setdefault("corrections", []).append(create_correction_event(item, signal, note))
    return state


def derived_preferences(state: dict[str, Any]) -> list[dict[str, Any]]:
    explicit = [correction_to_preference(event) for event in persistable_corrections(state)]
    existing = state.get("preferences", [])
    explicit_keys = {row["key"] for row in explicit}
    return explicit + [row for row in existing if row.get("key") not in explicit_keys]
