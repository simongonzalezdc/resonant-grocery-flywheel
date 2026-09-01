"""Tests for the capture-visit CLI."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest


@pytest.fixture
def empty_state_path(tmp_path):
    """A fresh state file with no pre-existing visits."""
    return tmp_path / "state.json"

def test_capture_visit_appends_visit(empty_state_path):
    empty_state_path.write_text('{"visits": []}')
    result = subprocess.run(
        [
            sys.executable, "-m", "grocery_flywheel.capture_visit",
            str(empty_state_path),
            "--type", "in_store",
            "--started-at", "2026-06-07T10:00",
            "--duration-min", "45",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    state = json.loads(empty_state_path.read_text())
    assert len(state["visits"]) == 1
    visit = state["visits"][0]
    assert visit["visit_type"] == "in_store"
    assert visit["duration_min"] == 45


def test_capture_visit_rejects_unknown_type(empty_state_path):
    empty_state_path.write_text('{"visits": []}')
    result = subprocess.run(
        [
            sys.executable, "-m", "grocery_flywheel.capture_visit",
            str(empty_state_path),
            "--type", "spaceship",
            "--started-at", "2026-06-07T10:00",
            "--duration-min", "30",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_capture_visit_accepts_optional_notes(empty_state_path):
    empty_state_path.write_text('{"visits": []}')
    result = subprocess.run(
        [
            sys.executable, "-m", "grocery_flywheel.capture_visit",
            str(empty_state_path),
            "--type", "pickup",
            "--started-at", "2026-06-07T18:00",
            "--duration-min", "10",
            "--notes", "example note",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    state = json.loads(empty_state_path.read_text())
    assert state["visits"][0]["notes"] == "example note"
