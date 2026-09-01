from __future__ import annotations

from typing import Any

from .optimization import rank_candidates


SOURCING_LIBRARY = {
    "coffee": [
        {
            "source": "Online bulk pack",
            "unit_price_multiplier": 0.86,
            "savings": "14%",
            "constraints": ["bulk storage", "availability changes"],
            "confidence": "medium",
            "trip_friction": 0.1,
            "quality_score": 0.75,
        },
        {
            "source": "Warehouse club",
            "unit_price_multiplier": 0.82,
            "savings": "18%",
            "constraints": ["membership", "bulk storage"],
            "confidence": "low",
            "trip_friction": 0.7,
            "quality_score": 0.7,
        },
    ],
    "critical_household_essential": [
        {
            "source": "Warehouse or online refill",
            "unit_price_multiplier": 0.72,
            "savings": "28%",
            "constraints": ["membership or shipping", "storage"],
            "confidence": "medium",
            "trip_friction": 0.4,
            "quality_score": 0.7,
        }
    ],
    "pantry_base": [
        {
            "source": "Bulk pantry buy",
            "unit_price_multiplier": 0.9,
            "savings": "10%",
            "constraints": ["storage", "slower payback"],
            "confidence": "medium",
            "trip_friction": 0.2,
            "quality_score": 0.65,
        }
    ],
}


def should_research_item(item: dict[str, Any]) -> bool:
    role = str(item.get("role", ""))
    category = str(item.get("category", "")).lower()
    spend = float(item.get("spend", 0) or 0)
    name = str(item.get("name", "")).lower()
    if role in SOURCING_LIBRARY:
        return True
    if spend >= 8 and any(token in category or token in name for token in ["coffee", "soap", "detergent", "rice"]):
        return True
    return bool(item.get("recurring"))


def current_unit_price(item: dict[str, Any]) -> float:
    unit_price = item.get("unit_price")
    if unit_price not in (None, ""):
        return float(unit_price)
    spend = float(item.get("spend", 0) or 0)
    amount = item.get("size", {}).get("amount")
    quantity = float(item.get("quantity", 1) or 1)
    if amount:
        return round(spend / (float(amount) * quantity), 4)
    return round(spend / quantity, 4) if quantity else spend


def build_sourcing_research(
    items: list[dict[str, Any]],
    *,
    objective: str = "balanced_roi",
    checked_date: str,
    storage_available: bool = True,
    subscriptions_opt_in: bool = False,
) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        if not should_research_item(item):
            continue
        role = str(item.get("role", ""))
        library = SOURCING_LIBRARY.get(role, SOURCING_LIBRARY.get("pantry_base", []))
        current = current_unit_price(item)
        alternatives = []
        for alt in library:
            constraints = list(alt["constraints"])
            trip_friction = float(alt.get("trip_friction", 0))
            if "storage" in " ".join(constraints).lower() and not storage_available:
                trip_friction += 1.0
                constraints.append("storage not confirmed")
            candidate_unit = round(current * float(alt["unit_price_multiplier"]), 4)
            savings_amount = max(0.0, current - candidate_unit)
            savings_pct = round((savings_amount / current) * 100, 2) if current else 0.0
            if "subscription" in str(alt.get("source", "")).lower() and not subscriptions_opt_in:
                constraints.append("subscription not recommended without opt-in")
                trip_friction += 2.0
            alternatives.append(
                {
                    "source": alt["source"],
                    "unit_price": candidate_unit,
                    "savings": alt.get("savings", f"{savings_pct:.0f}%"),
                    "savings_pct": savings_pct,
                    "savings_amount": round(savings_amount, 4),
                    "constraints": constraints,
                    "confidence": alt.get("confidence", "medium"),
                    "checked_date": checked_date,
                    "trip_friction": trip_friction,
                    "quality_score": alt.get("quality_score", 0.6),
                    "decision_friction": 0.35 if "Online" in alt["source"] else 0.65,
                    "dietary_status": item.get("dietary_status", "safe"),
                }
            )
        ranked = rank_candidates(alternatives, objective)
        if not ranked:
            continue
        best = ranked[0]
        dietary_status = item.get("dietary_status", "safe")
        worth_it = (
            dietary_status == "safe"
            and best["savings_pct"] >= 10
            and best["trip_friction"] < 1.0
        )
        rows.append(
            {
                "item": item["name"],
                "current_source": item.get("source_provenance", {}).get("retailer")
                or item.get("source", "Imported retailer"),
                "current_unit_price": current,
                "recommendation": sourcing_recommendation(dietary_status, worth_it),
                "dietary_status": dietary_status,
                "alternatives": ranked,
                "trigger": "recurring_or_high_leverage",
                "schema_version": item.get("schema_version"),
            }
        )
    return rows


def sourcing_recommendation(dietary_status: str, worth_it: bool) -> str:
    if dietary_status == "blocked":
        return "Do not buy until dietary conflict is resolved"
    if dietary_status == "needs_review":
        return "Needs dietary review before buying"
    if dietary_status == "warn":
        return "Review dietary warning before buying"
    return (
        "Worth checking alternate source"
        if worth_it
        else "Keep with normal store unless bundled into another trip"
    )
