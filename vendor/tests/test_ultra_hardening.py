"""Regressions for the 2026-08-14 adversarial-QA hardening pass.

Each test pins one finding from the three-way review (mine + GPT/Codex +
Kimi; see the UltraQA report). Grok ran too late for triage — findings
here are the consensus set.
"""

from __future__ import annotations

import io
import json
from datetime import date

from grocery_flywheel.core import analyze_state, first_wow, rank_substitutions
from grocery_flywheel.dietary import (
    EVIDENCE_STALE_DAYS,
    evaluate_item_for_restriction,
)
from grocery_flywheel.model.contract import validate_canonical_state
from grocery_flywheel.mcp_server import serve
from grocery_flywheel.normalization import normalize_item


# --- dietary fail-open (Kimi #13 + Codex #1) -----------------------------

def _item_with_evidence(checked: str):
    return {
        "name": "Granola bar",
        "schema_version": "2026-08-14.mvp2",
        "product_evidence": [{
            "evidence_type": "label_photo",
            "source": "user",
            "checked_date": checked,
            "ingredients": ["oats", "honey"],
        }],
    }


def test_stale_evidence_is_not_current_for_critical_restrictions():
    from datetime import timedelta
    today = date(2026, 8, 14)
    stale_date = (today - timedelta(days=EVIDENCE_STALE_DAYS + 1)).isoformat()
    result = evaluate_item_for_restriction(
        _item_with_evidence(stale_date), "p1",
        {"value": "peanut_allergy"}, today=today,
    )
    assert result["result"] == "needs_review"
    assert result["evidence_status"] == "stale"


def test_fresh_evidence_still_evaluates():
    result = evaluate_item_for_restriction(
        _item_with_evidence("2026-08-01"), "p1",
        {"value": "peanut_allergy"}, today=date(2026, 8, 14),
    )
    assert result["result"] == "safe"  # label present, no peanut token
    nutty = _item_with_evidence("2026-08-01")
    nutty["product_evidence"][0]["ingredients"] = ["oats", "peanut"]
    assert evaluate_item_for_restriction(
        nutty, "p1", {"value": "peanut_allergy"}, today=date(2026, 8, 14)
    )["result"] == "blocked"


def test_unrecognized_critical_restriction_never_evaluates_safe():
    result = evaluate_item_for_restriction(
        _item_with_evidence("2026-08-01"), "p1",
        {"value": "", "safety_tier": "critical"}, today=date(2026, 8, 14),
    )
    assert result["result"] == "needs_review"
    assert result["evidence_status"] == "unrecognized_restriction"


# --- ranking fail-open (Kimi #14) ----------------------------------------

def test_blocked_substitutions_never_rank_first_even_for_fewer_trips():
    rows = [
        {"current": "A", "candidate": "SAFE but far", "current_unit_price": 3.0,
         "candidate_unit_price": 1.0, "fit": "same", "trip_friction": 3.0,
         "candidate_dietary_status": "safe"},
        {"current": "B", "candidate": "BLOCKED next door", "current_unit_price": 3.0,
         "candidate_unit_price": 1.0, "fit": "better", "trip_friction": 0.0,
         "candidate_dietary_status": "blocked"},
    ]
    ranked = rank_substitutions(rows, "fewer_trips", dietary_profiles=[])
    assert ranked[0]["candidate"] != "BLOCKED next door"
    assert any(r["candidate"] == "BLOCKED next door" for r in ranked)  # still visible


# --- analysis correctness (Kimi #4, #5 / Codex #10) ----------------------

def test_first_wow_sums_all_sourcing_rows():
    analysis = {
        "sourcing_research": [
            {"item": "Coffee", "alternatives": [{"source": "S1", "savings_amount": 1.5}]},
            {"item": "Soap", "alternatives": [{"source": "S2", "savings_amount": 2.5}]},
        ],
        "substitutions": [{"savings_amount": 0.5}],
    }
    assert first_wow(analysis)["estimated_unit_savings"] == 4.5
    assert first_wow(analysis)["best_sourcing_move"].startswith("Soap")  # largest savings wins


def test_run_sheet_carries_schema_version():
    state = {
        "as_of": "2026-06-10",
        "schema_version": "2026-08-14.mvp2",
        "order": {"store": "S", "date": "2026-06-01", "total": 10.0},
    }
    analysis = analyze_state(state)
    assert analysis["schema_version"] == "2026-08-14.mvp2"
    assert analysis["run_sheet"]["schema_version"] == "2026-08-14.mvp2"


# --- contract hardening (Kimi #10/#11 / Codex #8/#9) ---------------------

def _valid_state():
    return {
        "schema_version": "2026-08-14.mvp2",
        "as_of": "2026-06-10",
        "order": {"schema_version": "2026-08-14.mvp2", "store": "S",
                  "date": "2026-06-01", "total": 10.0},
        "privacy": {"purchase_history": "sensitive_purchase_history"},
        "consent": {"correction_telemetry": "local_only", "hosted_sync": False,
                    "retailer_session_storage": "none", "password_storage": "forbidden"},
        "items": [normalize_item({"name": "X", "spend": 1.0}, source="t")],
    }


def test_added_on_null_rejected():
    state = _valid_state()
    state["items"][0]["added_on"] = None
    errors = validate_canonical_state(state)
    assert any("added_on" in e for e in errors)


def test_nan_spend_rejected():
    state = _valid_state()
    state["items"][0]["spend"] = float("nan")
    assert any("numeric" in e for e in validate_canonical_state(state))


def test_negative_spend_rejected():
    state = _valid_state()
    state["items"][0]["spend"] = -3.0
    assert any("non-negative" in e for e in validate_canonical_state(state))


# --- MCP protocol (Kimi #16 / Codex #5/#6) -------------------------------

def _run_lines(*lines: str) -> list[dict]:
    stdin = io.StringIO("".join(line + "\n" for line in lines))
    stdout = io.StringIO()
    serve(stdin, stdout)
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


def test_non_object_request_gets_32600():
    replies = _run_lines("[1, 2]", '"just a string"')
    assert all(r["error"]["code"] == -32600 for r in replies)


def test_explicit_null_id_is_answered_not_swallowed():
    replies = _run_lines(json.dumps({"jsonrpc": "2.0", "id": None, "method": "tools/list"}))
    assert len(replies) == 1 and replies[0]["id"] is None


def test_notification_still_silent():
    replies = _run_lines(json.dumps({"jsonrpc": "2.0", "method": "tools/list"}))
    assert replies == []


def test_arguments_as_list_gets_32602():
    replies = _run_lines(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "analyze_replenishment_state", "arguments": [1]},
    }))
    assert replies[0]["error"]["code"] == -32602


def test_oversized_line_rejected_before_parse():
    replies = _run_lines("x" * (17 * 1024 * 1024))
    assert replies[0]["error"]["code"] == -32600


# --- normalization (Kimi #7) ----------------------------------------------

def test_empty_string_numerics_treated_as_absent():
    item = normalize_item(
        {"name": "X", "spend": 5.0, "unit_price": "", "added_on": ""}, source="t"
    )
    assert item["unit_price"] is None
    assert "added_on" not in item  # "" counts as absent → baseline


def test_depletion_fields_survive_import():
    item = normalize_item(
        {"name": "X", "spend": 5.0, "units_total": 6, "units_remaining": 2,
         "storage": "pantry", "recurring": True},
        source="t",
    )
    assert item["units_total"] == 6 and item["units_remaining"] == 2
    assert item["storage"] == "pantry" and item["recurring"] is True


# --- dashboard JS round-trip (Kimi #15) -----------------------------------

def test_correction_capture_emits_date_only_created_at():
    from grocery_flywheel.rendering import render_dashboard
    state = {
        "as_of": "2026-06-10",
        "order": {"store": "S", "date": "2026-06-01", "total": 1.0},
        "items": [{"name": "x", "spend": 1.0}],
        "consent": {"correction_telemetry": "local_only", "hosted_sync": False,
                    "retailer_session_storage": "none", "password_storage": "forbidden"},
    }
    html = render_dashboard(analyze_state(state))
    assert "toISOString().slice(0, 10)" in html
