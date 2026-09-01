from grocery_flywheel.optimization import rank_candidates


def candidates():
    return [
        {
            "source": "Cheap split trip",
            "savings_pct": 35,
            "savings_amount": 4,
            "trip_friction": 0.95,
            "quality_score": 0.4,
            "decision_friction": 0.8,
            "confidence": "medium",
            "dietary_status": "safe",
        },
        {
            "source": "Normal store safer item",
            "savings_pct": 5,
            "savings_amount": 1,
            "trip_friction": 0.0,
            "quality_score": 0.7,
            "decision_friction": 0.1,
            "confidence": "high",
            "dietary_status": "safe",
        },
        {
            "source": "Unsafe bargain",
            "savings_pct": 50,
            "savings_amount": 8,
            "trip_friction": 0.1,
            "quality_score": 0.5,
            "decision_friction": 0.3,
            "confidence": "high",
            "dietary_status": "blocked",
        },
    ]


def test_objective_changes_top_recommendation():
    assert rank_candidates(candidates(), "lowest_cost")[0]["source"] == "Cheap split trip"
    assert rank_candidates(candidates(), "fewer_trips")[0]["source"] == "Normal store safer item"
    assert rank_candidates(candidates(), "lowest_decision_fatigue")[0]["source"] == "Normal store safer item"


def test_allergy_safe_prioritizes_safety_above_savings():
    ranked = rank_candidates(candidates(), "allergy_safe")

    assert ranked[0]["source"] == "Normal store safer item"
    assert ranked[-1]["source"] == "Unsafe bargain"
