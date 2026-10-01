"""Ticket 05 merge semantics: the canonical contract keeps the main
lineage's freshness fields and added_on presence semantics intact."""

from __future__ import annotations

import json
from pathlib import Path

from grocery_flywheel.cli import main
from grocery_flywheel.model.contract import SCHEMA_VERSION, validate_canonical_state
from grocery_flywheel.normalization import normalize_item

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_added_on_presence_semantics_preserved():
    top_up = normalize_item(
        {"name": "Trail mix", "spend": 6.0, "added_on": "2026-05-30"}, source="test"
    )
    baseline = normalize_item({"name": "Rice", "spend": 4.0}, source="test")
    assert top_up["added_on"] == "2026-05-30"      # present = top-up
    assert "added_on" not in baseline               # absent = baseline, no nulls


def test_freshness_fields_pass_through_normalization():
    item = normalize_item(
        {
            "name": "Olive oil", "spend": 9.0,
            "pricing_status": "priced", "last_price_check": "2026-05-25",
            "added_on": "2026-05-20",
        },
        source="test",
    )
    assert item["pricing_status"] == "priced"
    assert item["last_price_check"] == "2026-05-25"
    assert validate_canonical_state({
        "schema_version": SCHEMA_VERSION,
        "as_of": "2026-05-26",
        "order": {"schema_version": SCHEMA_VERSION, "store": "S", "date": "2026-05-20", "total": 9.0},
        "privacy": {"purchase_history": "sensitive_purchase_history"},
        "consent": {"correction_telemetry": "local_only", "hosted_sync": False,
                    "retailer_session_storage": "none", "password_storage": "forbidden"},
        "items": [item],
    }) == []


def test_added_on_must_be_iso_when_present():
    item = normalize_item({"name": "X", "spend": 1.0}, source="test")
    item["added_on"] = "31/31/2026"
    errors = validate_canonical_state({
        "schema_version": SCHEMA_VERSION,
        "as_of": "2026-05-26",
        "order": {"schema_version": SCHEMA_VERSION, "store": "S", "date": "2026-05-20", "total": 1.0},
        "privacy": {"purchase_history": "sensitive_purchase_history"},
        "consent": {"correction_telemetry": "local_only", "hosted_sync": False,
                    "retailer_session_storage": "none", "password_storage": "forbidden"},
        "items": [item],
    })
    assert any("added_on" in e and "ISO" in e for e in errors)


def test_cli_import_normalized_end_to_end(tmp_path: Path, capsys):
    payload = REPO_ROOT / "examples" / "imports" / "example-history.json"
    out = tmp_path / "state.json"
    main(argv=["import", "normalized", str(payload), "--output", str(out)])
    state = json.loads(out.read_text())
    assert state["schema_version"] == SCHEMA_VERSION
    assert validate_canonical_state(state) == []
    assert "schema 2026-08-14.mvp2" in capsys.readouterr().out


def test_cli_import_csv_end_to_end(tmp_path: Path):
    payload = REPO_ROOT / "examples" / "imports" / "example-history.csv"
    out = tmp_path / "state.json"
    main(argv=["import", "csv", str(payload), "--output", str(out)])
    state = json.loads(out.read_text())
    assert state["items"]
    assert validate_canonical_state(state) == []
