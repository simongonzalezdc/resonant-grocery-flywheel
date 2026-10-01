import json
from pathlib import Path

from grocery_flywheel.dietary import evaluate_dietary_profiles
from grocery_flywheel.importers import import_normalized_history


ROOT = Path(__file__).resolve().parents[1]


def imported_items_and_profiles():
    payload = json.loads((ROOT / "examples" / "imports" / "example-history.json").read_text())
    state = import_normalized_history(payload)
    return state["items"], state["dietary_profiles"]


def test_safety_critical_missing_evidence_returns_needs_review_not_safe():
    items, profiles = imported_items_and_profiles()
    evaluations = evaluate_dietary_profiles(items, profiles)

    mystery = [
        row
        for row in evaluations
        if row["item"] == "Mystery frozen meal" and row["restriction"] == "peanut_allergy"
    ][0]
    assert mystery["result"] == "needs_review"
    assert mystery["evidence_status"] == "missing"


def test_documented_safety_critical_shape_normalizes_to_needs_review():
    item = {"name": "Unknown snack", "product_evidence": [], "schema_version": "test"}
    profile = {
        "profile_id": "doc-shape",
        "restrictions": [
            {
                "type": "food_allergy",
                "value": "peanuts",
                "safety_tier": "safety_critical",
                "behavior": "block_until_review",
            }
        ],
    }

    result = evaluate_dietary_profiles([item], [profile])[0]

    assert result["restriction"] == "peanut_allergy"
    assert result["safety_tier"] == "critical"
    assert result["result"] == "needs_review"


def test_safety_critical_safe_requires_current_product_evidence():
    items, profiles = imported_items_and_profiles()
    evaluations = evaluate_dietary_profiles(items, profiles)

    milk = [
        row
        for row in evaluations
        if row["item"] == "Chocolate protein milk" and row["restriction"] == "peanut_allergy"
    ][0]
    assert milk["result"] == "safe"
    assert milk["evidence_status"] == "current"


def test_safety_critical_missing_evidence_type_is_missing_not_safe():
    item = {
        "name": "Untyped package",
        "schema_version": "test",
        "product_evidence": [
            {
                "source": "example package",
                "checked_date": "2026-05-26",
                "ingredients": ["oats"],
            }
        ],
    }
    profile = {
        "profile_id": "critical",
        "restrictions": [
            {
                "value": "peanut_allergy",
                "safety_tier": "critical",
                "behavior": "block",
            }
        ],
    }

    result = evaluate_dietary_profiles([item], [profile])[0]

    assert result["result"] == "needs_review"
    assert result["evidence_status"] == "missing"


def test_safety_critical_empty_label_content_is_ambiguous_not_safe():
    item = {
        "name": "Bare evidence shell",
        "schema_version": "test",
        "product_evidence": [
            {
                "evidence_type": "ingredient_label",
                "source": "example package",
                "checked_date": "2026-05-26",
                "ingredients": [],
                "allergen_statements": [],
                "certifications": [],
            }
        ],
    }
    profile = {
        "profile_id": "critical",
        "restrictions": [
            {
                "value": "peanut_allergy",
                "safety_tier": "critical",
                "behavior": "block",
            }
        ],
    }

    result = evaluate_dietary_profiles([item], [profile])[0]

    assert result["result"] == "needs_review"
    assert result["evidence_status"] == "ambiguous"


def test_safety_critical_whitespace_label_content_is_ambiguous_not_safe():
    item = {
        "name": "Whitespace evidence shell",
        "schema_version": "test",
        "product_evidence": [
            {
                "evidence_type": "ingredient_label",
                "source": "example package",
                "checked_date": "2026-05-26",
                "ingredients": ["", "  "],
                "allergen_statements": [],
                "certifications": [],
            }
        ],
    }
    profile = {
        "profile_id": "critical",
        "restrictions": [
            {
                "value": "peanut_allergy",
                "safety_tier": "critical",
                "behavior": "block",
            }
        ],
    }

    result = evaluate_dietary_profiles([item], [profile])[0]

    assert result["result"] == "needs_review"
    assert result["evidence_status"] == "ambiguous"


def test_safety_critical_null_label_content_is_ambiguous_not_safe():
    item = {
        "name": "Null evidence shell",
        "schema_version": "test",
        "product_evidence": [
            {
                "evidence_type": "ingredient_label",
                "source": "example package",
                "checked_date": "2026-05-26",
                "ingredients": [None],
                "allergen_statements": [],
                "certifications": [],
            }
        ],
    }
    profile = {
        "profile_id": "critical",
        "restrictions": [
            {
                "value": "peanut_allergy",
                "safety_tier": "critical",
                "behavior": "block",
            }
        ],
    }

    result = evaluate_dietary_profiles([item], [profile])[0]

    assert result["result"] == "needs_review"
    assert result["evidence_status"] == "ambiguous"


def test_allergy_conflict_blocks_before_savings():
    items, profiles = imported_items_and_profiles()
    evaluations = evaluate_dietary_profiles(items, profiles)

    peanut = [
        row
        for row in evaluations
        if row["item"] == "Peanut granola bars" and row["restriction"] == "peanut_allergy"
    ][0]
    assert peanut["result"] == "blocked"
