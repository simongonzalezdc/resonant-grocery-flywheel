from __future__ import annotations

from typing import Any


OBJECTIVES = {
    "lowest_cost": "Lowest cost",
    "fewer_trips": "Fewer trips",
    "balanced_roi": "Balanced ROI",
    "dietary_restrictions": "Dietary restrictions",
    "allergy_safe": "Allergy safe",
    "best_quality": "Best quality",
    "lowest_decision_fatigue": "Lowest decision fatigue",
}

CONFIDENCE_SCORE = {"high": 1.0, "medium": 0.65, "low": 0.25}
DIETARY_PENALTY = {"safe": 0.0, "warn": -2.0, "needs_review": -5.0, "blocked": -100.0}


def validate_objective(objective: str) -> str:
    if objective not in OBJECTIVES:
        allowed = ", ".join(sorted(OBJECTIVES))
        raise ValueError(f"unknown objective {objective!r}; expected one of: {allowed}")
    return objective


def objective_label(objective: str) -> str:
    return OBJECTIVES[validate_objective(objective)]


def score_candidate(candidate: dict[str, Any], objective: str) -> float:
    objective = validate_objective(objective)
    savings_pct = float(candidate.get("savings_pct", 0) or 0)
    savings_amount = float(candidate.get("savings_amount", 0) or 0)
    trip_friction = float(candidate.get("trip_friction", 0) or 0)
    quality = float(candidate.get("quality_score", 0.5) or 0.5)
    decision_friction = float(candidate.get("decision_friction", 0.5) or 0.5)
    confidence = CONFIDENCE_SCORE.get(str(candidate.get("confidence", "medium")), 0.65)
    dietary_status = str(candidate.get("dietary_status", "safe"))
    dietary = DIETARY_PENALTY.get(dietary_status, -1.0)

    if objective == "lowest_cost":
        return savings_pct * 1.6 + savings_amount * 0.5 + dietary
    if objective == "fewer_trips":
        return savings_pct * 0.1 + confidence - trip_friction * 8 + dietary * 0.2
    if objective == "dietary_restrictions":
        return dietary * 12 + confidence + savings_pct * 0.2
    if objective == "allergy_safe":
        return dietary * 30 + confidence + quality
    if objective == "best_quality":
        return quality * 10 + confidence + savings_pct * 0.2 + dietary
    if objective == "lowest_decision_fatigue":
        return (1 - decision_friction) * 10 + confidence - trip_friction * 3 + dietary
    return savings_pct + savings_amount * 0.25 + quality * 2 + confidence - trip_friction * 2 + dietary


def rank_candidates(candidates: list[dict[str, Any]], objective: str) -> list[dict[str, Any]]:
    validate_objective(objective)
    scored = []
    for candidate in candidates:
        row = dict(candidate)
        row["optimization_objective"] = objective
        row["optimization_score"] = round(score_candidate(row, objective), 4)
        scored.append(row)
    return sorted(scored, key=lambda row: row["optimization_score"], reverse=True)
