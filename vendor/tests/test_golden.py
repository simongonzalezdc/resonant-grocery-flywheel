"""Golden dashboard gates — dual goldens.

Golden 1 (legacy): the unversioned sample state must keep rendering via
the lenient defaulting path across every schema change.
Golden 2 (canonical): the importer-produced canonical state must render
with its richer panels. Diffs here mean rendered output changed: fix the
regression or regenerate deliberately with human review.
"""

from __future__ import annotations

import json
from pathlib import Path

from grocery_flywheel.core import analyze_state
from grocery_flywheel.importers import import_normalized_history
from grocery_flywheel.render import render_dashboard

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = REPO_ROOT / "tests" / "golden"


def _assert_matches_golden(html: str, golden: Path) -> None:
    assert html == golden.read_text(), (
        f"Rendered dashboard diverged from {golden.name}. "
        "If intentional: regenerate the golden and note why in the PR."
    )


def test_legacy_sample_dashboard_matches_golden():
    state = json.loads((REPO_ROOT / "examples" / "sample_state.json").read_text())
    _assert_matches_golden(render_dashboard(analyze_state(state)),
                           GOLDEN_DIR / "sample_dashboard.html")


def test_canonical_imported_dashboard_matches_golden():
    payload = json.loads((REPO_ROOT / "examples" / "imports" / "example-history.json").read_text())
    state = import_normalized_history(payload)
    assert state["schema_version"] == "2026-08-14.mvp2"
    _assert_matches_golden(render_dashboard(analyze_state(state)),
                           GOLDEN_DIR / "canonical_dashboard.html")
