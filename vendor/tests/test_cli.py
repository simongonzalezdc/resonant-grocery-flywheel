"""In-process entry-point coverage for the dashboard CLI."""

from __future__ import annotations

import json
from pathlib import Path

from grocery_flywheel.cli import main


def test_main_renders_dashboard_from_state_file(tmp_path: Path, capsys):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "as_of": "2026-06-10",
        "order": {"store": "Store", "date": "2026-06-01", "total": 100.0},
        "items": [{"name": "Milk", "role": "protein", "spend": 4.0,
                   "consumed_fraction": 0.5}],
    }))
    out_path = tmp_path / "nested" / "out.html"

    main(argv=[str(state_path), "--output", str(out_path)])

    html = out_path.read_text()
    assert html.startswith("<!doctype html>")
    assert "Grocery Flywheel" in html
    assert f"wrote {out_path}" in capsys.readouterr().out


def test_main_rejects_missing_output(tmp_path: Path):
    import pytest

    state_path = tmp_path / "state.json"
    state_path.write_text("{}")
    with pytest.raises(SystemExit):
        main(argv=[str(state_path)])
