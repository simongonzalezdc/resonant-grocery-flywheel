from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from .corrections import derived_preferences
from .cost_log import visits_summary
from .dietary import evaluate_dietary_profiles, has_critical_dietary_profile
from .draft import generate_cart_plan, generate_run_sheet
from .easy_food import easy_food_summary
from .freshness import summarize_freshness
from .model import clamp as _clamp
from .model import consumed_fraction
from .optimization import objective_label, rank_candidates, validate_objective
from .sourcing import build_sourcing_research


def item_consumed_fraction(item: dict[str, Any]) -> float:
    """Return the best-known consumed fraction for an item.

    Delegates to :func:`grocery_flywheel.model.consumed_fraction` — the
    single implementation every panel shares.
    """
    return consumed_fraction(item)


def clamp(value: float) -> float:
    """Back-compat re-export of the model package's clamp (single home)."""
    return _clamp(value)


def analyze_state(state: dict[str, Any], objective: str | None = None) -> dict[str, Any]:
    """Analyze a replenishment state (lenient read — no contract enforcement).

    Objective-awareness is opt-in: pass ``objective`` or set
    ``state["objective"]`` to rank substitutions by that objective and
    auto-generate sourcing research when missing. Without it, legacy
    behavior is preserved bit-for-bit (substitution_score ordering,
    sourcing passthrough) so old states keep rendering identically.
    """
    objective = objective or state.get("objective")
    if objective is not None:
        objective = validate_objective(objective)

    order = state["order"]
    items = state.get("items", [])
    order_total = float(order["total"])
    as_of = date.fromisoformat(state["as_of"])
    order_date = date.fromisoformat(order["date"])
    # Surface data problems instead of silently clamping them away: a
    # future-dated order used to disappear into max(1, ...).
    data_warnings: list[str] = []
    if as_of < order_date:
        data_warnings.append(
            f"order date {order['date']} is after as_of {state['as_of']}; "
            "runway is unreliable until the dates are corrected"
        )
    days_elapsed = max(1, (as_of - order_date).days)

    item_rows = []
    consumed_value = 0.0
    role_spend: dict[str, float] = defaultdict(float)
    role_consumed: dict[str, float] = defaultdict(float)

    for item in items:
        spend = float(item.get("spend", 0))
        role = str(item.get("role", "unknown"))
        item_consumed = consumed_fraction(item)
        consumed = spend * item_consumed
        consumed_value += consumed
        role_spend[role] += spend
        role_consumed[role] += consumed
        item_rows.append(
            {
                "name": item["name"],
                "role": role,
                "category": item.get("category", ""),
                "storage": item.get("storage", ""),
                "spend": spend,
                "unit_price": item.get("unit_price"),
                "quantity": item.get("quantity", 1),
                "confidence": item.get("confidence", "medium"),
                "privacy_class": item.get("privacy_class", "sensitive_purchase_history"),
                "product_evidence": item.get("product_evidence", []),
                "consumed_fraction": item_consumed,
                "consumed_value": consumed,
                "notes": item.get("notes", ""),
                "pricing_status": item.get("pricing_status"),
                "last_price_check": item.get("last_price_check"),
                "added_on": item.get("added_on"),
                "schema_version": item.get("schema_version"),
            }
        )

    known_consumed_fraction = consumed_value / order_total if order_total else 0.0
    estimated_total_days = (
        round(days_elapsed / known_consumed_fraction, 1)
        if known_consumed_fraction > 0
        else None
    )
    estimated_days_remaining = (
        round(max(0.0, estimated_total_days - days_elapsed), 1)
        if estimated_total_days is not None
        else None
    )

    dietary_profiles = state.get("dietary_profiles", [])
    dietary_evaluations = evaluate_dietary_profiles(
        item_rows, dietary_profiles, today=as_of
    )
    dietary_status_by_item = item_dietary_statuses(dietary_evaluations)
    for item in item_rows:
        item["dietary_status"] = dietary_status_by_item.get(item["name"], "safe")

    if objective is not None:
        substitutions = rank_substitutions(
            state.get("substitutions", []),
            objective,
            dietary_status_by_item=dietary_status_by_item,
            dietary_profiles=dietary_profiles,
        )
    else:
        substitutions = sorted(
            state.get("substitutions", []),
            key=lambda row: substitution_score(row),
            reverse=True,
        )

    sourcing_research = state.get("sourcing_research", [])
    if objective is not None and not sourcing_research:
        sourcing_research = build_sourcing_research(
            item_rows,
            objective=objective,
            checked_date=state["as_of"],
            storage_available=state.get("storage", {}).get("bulk_available", True),
            subscriptions_opt_in=state.get("preferences_config", {}).get(
                "subscriptions_opt_in", False
            ),
        )

    analysis = {
        "schema_version": state.get("schema_version"),
        "order": order,
        "as_of": state["as_of"],
        "objective": objective,
        "objective_label": objective_label(objective) if objective else None,
        "data_warnings": data_warnings,
        "inventory_surface": state.get("inventory_surface", {}),
        "acquisition_channel": state.get("acquisition_channel", "unknown"),
        "days_elapsed": days_elapsed,
        "items": item_rows,
        "consumed_value": round(consumed_value, 2),
        "known_consumed_fraction": round(known_consumed_fraction, 4),
        "estimated_total_days": estimated_total_days,
        "estimated_days_remaining": estimated_days_remaining,
        "role_summary": summarize_roles(role_spend, role_consumed),
        "freshness": summarize_freshness(
            items, state.get("sourcing_research", []), today=as_of,
        ),
        "easy_food": easy_food_summary(state, today=as_of),
        "visits_summary": visits_summary(
            state, hourly_value=state.get("hourly_value")
        ),
        "preferences": derived_preferences(state),
        "dietary_profiles": dietary_profiles,
        "dietary_evaluations": dietary_evaluations,
        "substitutions": substitutions,
        "sourcing_research": sourcing_research,
        "pulses": state.get("pulses", []),
        "consent": state.get("consent", {}),
        "shopping_mode": state.get("shopping_mode", "pickup"),
    }
    analysis["first_wow"] = first_wow(analysis)
    analysis["cart_plan"] = generate_cart_plan(
        analysis, mode=analysis["shopping_mode"]
    )
    analysis["run_sheet"] = generate_run_sheet(analysis)
    return analysis


def first_wow(analysis: dict[str, Any]) -> dict[str, Any]:
    sourcing = analysis.get("sourcing_research", [])
    total_savings = 0.0
    best_label = "No sourcing move yet"
    best_savings = -1.0
    for row in sourcing:
        alt = (row.get("alternatives") or [{}])[0]
        row_savings = float(alt.get("savings_amount", 0) or 0)
        total_savings += row_savings
        if row_savings > best_savings:
            best_savings = row_savings
            best_label = f"{row['item']} at {alt.get('source', 'alternate source')}"
    for row in analysis.get("substitutions", []):
        total_savings += max(0.0, float(row.get("savings_amount", 0) or 0))
    return {
        "estimated_unit_savings": round(total_savings, 2),
        "best_sourcing_move": best_label,
        "headline": "Savings and sourcing options are ready for review"
        if total_savings > 0
        else "Runway and sourcing baseline are ready",
    }


def substitution_score(row: dict[str, Any]) -> float:
    fit = row.get("fit", "")
    fit_bonus = {
        "better": 2.0,
        "better_if_storage_ok": 1.0,
        "same": 0.0,
        "worse": -2.0,
    }.get(fit, 0.0)
    current = float(row.get("current_unit_price", 0) or 0)
    candidate = float(row.get("candidate_unit_price", 0) or 0)
    unit_delta = current - candidate
    return fit_bonus + unit_delta


def item_dietary_statuses(evaluations: list[dict[str, Any]]) -> dict[str, str]:
    severity = {"safe": 0, "warn": 1, "needs_review": 2, "blocked": 3}
    statuses: dict[str, str] = {}
    for row in evaluations:
        item = row["item"]
        result = row.get("result", "safe")
        if severity.get(result, 0) > severity.get(statuses.get(item, "safe"), 0):
            statuses[item] = result
    return statuses


def rank_substitutions(
    rows: list[dict[str, Any]],
    objective: str,
    *,
    dietary_status_by_item: dict[str, str] | None = None,
    dietary_profiles: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    dietary_status_by_item = dietary_status_by_item or {}
    dietary_profiles = dietary_profiles or []
    critical_dietary = has_critical_dietary_profile(dietary_profiles)
    candidates = []
    for row in rows:
        current = float(row.get("current_unit_price", 0) or 0)
        candidate = float(row.get("candidate_unit_price", 0) or 0)
        savings_amount = current - candidate
        savings_pct = (savings_amount / current) * 100 if current else 0
        candidate_evidence = list(row.get("candidate_product_evidence") or row.get("product_evidence") or [])
        dietary_status = substitution_dietary_status(
            row,
            dietary_status_by_item=dietary_status_by_item,
            dietary_profiles=dietary_profiles,
            critical_dietary=critical_dietary,
            candidate_evidence=candidate_evidence,
        )
        enriched = dict(row)
        enriched.update(
            {
                "savings_amount": round(savings_amount, 4),
                "savings_pct": round(savings_pct, 2),
                "trip_friction": row.get("trip_friction", 0.2),
                "quality_score": substitution_quality_score(str(row.get("fit", ""))),
                "decision_friction": row.get("decision_friction", 0.3),
                "confidence": row.get("confidence", "medium"),
                "dietary_status": dietary_status,
                "evidence_status": substitution_evidence_status(
                    dietary_status=dietary_status,
                    candidate_evidence=candidate_evidence,
                    critical_dietary=critical_dietary,
                ),
            }
        )
        candidates.append(enriched)
    ranked = rank_candidates(candidates, objective) if candidates else []
    # Dietary-blocked candidates can never rank first, whatever the
    # objective weights — a blocked item at the top of a cost- or
    # trip-optimized list reads as a recommendation. Keep them visible
    # (the panel badges them) but demote them below every non-blocked row.
    not_blocked = [row for row in ranked if row.get("dietary_status") != "blocked"]
    blocked = [row for row in ranked if row.get("dietary_status") == "blocked"]
    order_key = lambda row: (row["optimization_score"], substitution_score(row))  # noqa: E731
    return sorted(not_blocked, key=order_key, reverse=True) + sorted(
        blocked, key=order_key, reverse=True
    )


def substitution_dietary_status(
    row: dict[str, Any],
    *,
    dietary_status_by_item: dict[str, str],
    dietary_profiles: list[dict[str, Any]],
    critical_dietary: bool,
    candidate_evidence: list[dict[str, Any]],
) -> str:
    candidate_name = str(row.get("candidate", ""))
    explicit_status = row.get("candidate_dietary_status") or row.get("dietary_status")
    if candidate_name in dietary_status_by_item:
        return dietary_status_by_item[candidate_name]
    if critical_dietary:
        if candidate_evidence:
            candidate_item = {
                "name": candidate_name,
                "schema_version": row.get("schema_version"),
                "product_evidence": candidate_evidence,
            }
            evaluations = evaluate_dietary_profiles([candidate_item], dietary_profiles)
            return item_dietary_statuses(evaluations).get(candidate_name, "needs_review")
        if explicit_status in {"blocked", "needs_review", "warn"}:
            return str(explicit_status)
        return "needs_review"
    return (
        str(explicit_status)
        if explicit_status
        else dietary_status_by_item.get(row.get("current", ""), "safe")
    )


def substitution_evidence_status(
    *,
    dietary_status: str,
    candidate_evidence: list[dict[str, Any]],
    critical_dietary: bool,
) -> str:
    if candidate_evidence:
        return "candidate_evidence_current" if dietary_status == "safe" else "candidate_evidence_reviewed"
    if critical_dietary:
        return "missing_candidate_evidence"
    return "not_required"


def substitution_quality_score(fit: str) -> float:
    return {
        "better": 10.0,
        "same": 4.0,
        "better_if_storage_ok": 1.5,
        "worse": 0.0,
    }.get(fit, 1.0)


def summarize_roles(
    role_spend: dict[str, float], role_consumed: dict[str, float]
) -> list[dict[str, Any]]:
    rows = []
    for role in sorted(role_spend):
        spend = role_spend[role]
        consumed = role_consumed.get(role, 0.0)
        rows.append(
            {
                "role": role,
                "spend": round(spend, 2),
                "consumed": round(consumed, 2),
                "consumed_fraction": round(consumed / spend, 4) if spend else 0.0,
            }
        )
    return rows
