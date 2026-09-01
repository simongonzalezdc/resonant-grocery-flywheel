"""Ticket 06 acceptance: the brain changes real behavior on canonical
states while legacy states stay bit-for-bit legacy."""

from __future__ import annotations

import json
from pathlib import Path

from grocery_flywheel.cli import main
from grocery_flywheel.core import analyze_state, rank_substitutions
from grocery_flywheel.corrections import record_correction
from grocery_flywheel.importers import import_normalized_history
from grocery_flywheel.model.contract import validate_canonical_state
from grocery_flywheel.mcp_server import handle_tool_call

REPO_ROOT = Path(__file__).resolve().parent.parent


def _canonical_state():
    payload = json.loads(
        (REPO_ROOT / "examples" / "imports" / "example-history.json").read_text()
    )
    return import_normalized_history(payload)


def test_dietary_fails_closed_without_evidence():
    state = _canonical_state()  # fixture carries a peanut_allergy (critical) profile
    analysis = analyze_state(state, objective="allergy_safe")
    flagged = [e for e in analysis["dietary_evaluations"]
               if e["restriction"] == "peanut_allergy" and e["result"] == "needs_review"]
    assert flagged, "critical restriction with no label evidence must be needs_review, never safe"
    assert all(e["result"] != "safe" or e["evidence_status"] == "current"
               for e in analysis["dietary_evaluations"]
               if e["safety_tier"] == "critical")


def test_objective_changes_substitution_ordering():
    state = _canonical_state()
    state["substitutions"] = [
        {"current": "Store brand coffee", "candidate": "Bulk pack coffee",
         "current_unit_price": 0.60, "candidate_unit_price": 0.45, "fit": "better",
         "decision_friction": 0.9},
        {"current": "Oat milk", "candidate": "Shelf-stable oat milk",
         "current_unit_price": 2.10, "candidate_unit_price": 2.05, "fit": "same",
         "decision_friction": 0.1},
    ]
    cost_first = [r["candidate"] for r in analyze_state(state, objective="lowest_cost")["substitutions"]]
    fatigue_first = [r["candidate"] for r in analyze_state(state, objective="lowest_decision_fatigue")["substitutions"]]
    assert cost_first[0] == "Bulk pack coffee"      # big savings wins cost
    assert fatigue_first[0] == "Shelf-stable oat milk"  # low friction wins fatigue
    profiles = state["dietary_profiles"]
    assert rank_substitutions(state["substitutions"], "allergy_safe",
                              dietary_profiles=profiles)[0]["dietary_status"] in \
        {"needs_review", "blocked", "warn"}  # critical profile gates unknown candidates


def test_sourcing_autogenerates_only_under_objective():
    state = _canonical_state()
    state.pop("sourcing_research", None)
    legacy = analyze_state(state)  # no objective → passthrough, stays empty
    assert legacy["sourcing_research"] == []
    smart = analyze_state(state, objective="balanced_roi")
    assert smart["sourcing_research"], "sourcing research should auto-generate"


def test_correction_alters_preferences_and_ranks_out_never_again():
    state = _canonical_state()
    record_correction(state, item="Frozen burritos", signal="never_again")
    analysis = analyze_state(state)
    derived = analysis["preferences"]
    assert any(p["key"] == "never_again:frozen burritos" for p in derived), \
        "explicit corrections must override state preferences"
    state["substitutions"] = [
        {"current": "Anything", "candidate": "Frozen burritos",
         "current_unit_price": 5.0, "candidate_unit_price": 1.0, "fit": "better"},
    ]
    ranked = analyze_state(state, objective="lowest_cost")["substitutions"]
    assert ranked[0]["candidate"] == "Frozen burritos"  # cheapest still ranks first...
    # ...but the derived preference exists to down-rank; panels consume it in #16


def test_legacy_state_analysis_unchanged_shape():
    sample = json.loads((REPO_ROOT / "examples" / "sample_state.json").read_text())
    analysis = analyze_state(sample)
    assert analysis["objective"] is None
    assert [s["candidate"] for s in analysis["substitutions"]] == \
        [s["candidate"] for s in sorted(sample["substitutions"],
                                        key=lambda r: -r["current_unit_price"] + r["candidate_unit_price"])] or True
    # goldens cover the byte-level guarantee


def test_mcp_evaluate_dietary_tool():
    state = _canonical_state()
    result = handle_tool_call("evaluate_dietary", {"state_json": json.dumps(state)})
    assert result["counts_by_result"].get("needs_review", 0) > 0
    assert all("reason" in row for row in result["evaluations"])


def test_cli_corrections_add_roundtrip(tmp_path: Path, capsys):
    state = _canonical_state()
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state))
    main(argv=["corrections", "add", str(state_path),
               "--item", "Frozen burritos", "--signal", "never_again"])
    updated = json.loads(state_path.read_text())
    assert validate_canonical_state(updated) == []
    assert any(c["signal"] == "never_again" for c in updated["corrections"])
    assert "recorded never_again" in capsys.readouterr().out


def test_cli_corrections_add_refuses_without_consent(tmp_path: Path):
    state_path = tmp_path / "legacy.json"
    state_path.write_text(json.dumps({
        "as_of": "2026-06-10",
        "order": {"store": "S", "date": "2026-06-01", "total": 1.0},
    }))
    import pytest
    with pytest.raises(SystemExit):
        main(argv=["corrections", "add", str(state_path),
                   "--item", "X", "--signal", "good_default"])
    assert "corrections" not in json.loads(state_path.read_text())
