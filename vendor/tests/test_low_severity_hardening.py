"""Regressions for the six deferred low-severity QA findings (2026-08-16):

atomic writes, add_visit validation, crash-proof visits_summary, CSV
multi-order/parse handling, contract coverage for visits/profiles/
hourly_value/fractions, and future-dated-order warnings.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from grocery_flywheel.core import analyze_state
from grocery_flywheel.cost_log import add_visit, visits_summary
from grocery_flywheel.importers import import_csv_history
from grocery_flywheel.model.contract import validate_canonical_state
from grocery_flywheel.rendering import render_dashboard
from grocery_flywheel.state_io import write_state

REPO_ROOT = Path(__file__).resolve().parent.parent


# --- atomic writes + capture_visit routing -------------------------------

def test_write_state_is_atomic_and_leaves_no_temp(tmp_path: Path):
    target = tmp_path / "nested" / "state.json"
    write_state({"a": 1}, target)
    assert json.loads(target.read_text()) == {"a": 1}
    assert target.read_text().endswith("\n")
    leftovers = [p for p in tmp_path.rglob("*.tmp")]
    assert leftovers == []


def test_capture_visit_writes_via_state_io(tmp_path: Path):
    from grocery_flywheel.capture_visit import main
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"visits": []}))
    main(argv=[str(state_path), "--type", "in_store",
               "--started-at", "2026-06-07T10:00", "--duration-min", "30"])
    content = state_path.read_text()
    assert content.endswith("\n")
    assert len(json.loads(content)["visits"]) == 1


# --- add_visit validation -------------------------------------------------

def test_add_visit_rejects_garbage_timestamp():
    with pytest.raises(ValueError, match="ISO timestamp"):
        add_visit({}, visit_type="in_store", started_at="not-a-time", duration_min=5)


def test_add_visit_rejects_fractional_duration():
    with pytest.raises(ValueError, match="whole minutes"):
        add_visit({}, visit_type="in_store", started_at="2026-06-07T10:00",
                  duration_min=1.5)


# --- crash-proof visits_summary -------------------------------------------

def test_visits_summary_survives_garbage_duration():
    summary = visits_summary({"visits": [
        {"visit_type": "in_store", "started_at": "2026-06-07T10:00",
         "duration_min": "abc"},
        {"visit_type": "in_store", "started_at": "2026-06-08T10:00",
         "duration_min": 40},
    ]})
    assert summary["visit_count"] == 2          # the visit still counts
    assert summary["total_minutes"] == 40       # garbage contributes 0


# --- CSV importer ----------------------------------------------------------

def test_csv_multi_order_rejected_instead_of_collapsed(tmp_path: Path):
    csv_path = tmp_path / "multi.csv"
    csv_path.write_text(
        "store,order_date,name,spend\n"
        "Mart A,2026-05-01,Oil,4.00\n"
        "Mart B,2026-05-03,Rice,3.00\n"
    )
    with pytest.raises(ValueError, match="2 distinct orders"):
        import_csv_history(csv_path)


def test_csv_single_order_still_imports(tmp_path: Path):
    csv_path = tmp_path / "one.csv"
    csv_path.write_text("store,order_date,name,spend\nMart A,2026-05-01,Oil,4.00\n")
    state = import_csv_history(csv_path)
    assert validate_canonical_state(state) == []


def test_csv_oversized_field_is_a_clean_error(tmp_path: Path):
    csv_path = tmp_path / "huge.csv"
    csv_path.write_text("store,order_date,name,spend\nMart A,2026-05-01," + "x" * 200000 + ",4.00\n")
    with pytest.raises(ValueError, match="CSV could not be parsed"):
        import_csv_history(csv_path)


# --- contract coverage -----------------------------------------------------

def _valid_state():
    return {
        "schema_version": "2026-08-14.mvp2",
        "as_of": "2026-06-10",
        "order": {"schema_version": "2026-08-14.mvp2", "store": "S",
                  "date": "2026-06-01", "total": 10.0},
        "privacy": {"purchase_history": "sensitive_purchase_history"},
        "consent": {"correction_telemetry": "local_only", "hosted_sync": False,
                    "retailer_session_storage": "none", "password_storage": "forbidden"},
        "items": [{"schema_version": "2026-08-14.mvp2", "name": "X", "spend": 1.0,
                   "privacy_class": "sensitive_purchase_history", "confidence": "high"}],
    }


def test_visits_now_validated():
    state = _valid_state()
    state["visits"] = [{"visit_type": "in_store", "started_at": "garbage",
                        "duration_min": 30}]
    assert any("started_at" in e for e in validate_canonical_state(state))
    state["visits"] = [{"visit_type": "in_store", "started_at": "2026-06-07T10:00",
                        "duration_min": -5}]
    assert any("duration_min" in e for e in validate_canonical_state(state))


def test_retailer_profiles_and_hourly_value_validated():
    state = _valid_state()
    state["retailer_profiles"] = [42]
    assert any("retailer_profiles" in e for e in validate_canonical_state(state))
    state["retailer_profiles"] = ["retailer.example"]
    state["hourly_value"] = -10
    assert any("hourly_value" in e for e in validate_canonical_state(state))


def test_fraction_ranges_and_units_consistency_validated():
    state = _valid_state()
    state["items"][0]["consumed_fraction"] = 1.5
    assert any("within [0, 1]" in e for e in validate_canonical_state(state))
    state["items"][0]["consumed_fraction"] = 0.5
    state["items"][0]["units_total"] = 6
    state["items"][0]["units_remaining"] = 9
    assert any("exceed units_total" in e for e in validate_canonical_state(state))


# --- future-dated orders surface a warning ---------------------------------

def test_future_dated_order_warns_instead_of_silent_clamp():
    state = _valid_state()
    state["as_of"] = "2026-05-20"       # before order date 2026-06-01
    analysis = analyze_state(state)
    assert analysis["days_elapsed"] == 1
    assert any("after as_of" in w for w in analysis["data_warnings"])
    html = render_dashboard(analysis)
    assert "unreliable until the dates are corrected" in html


def test_normal_state_has_no_warnings():
    analysis = analyze_state(_valid_state())
    assert analysis["data_warnings"] == []
