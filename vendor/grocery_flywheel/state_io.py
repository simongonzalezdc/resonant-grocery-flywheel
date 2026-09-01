"""Shared state file and artifact IO.

The CLI and the MCP render tool previously each carried their own
read-state / mkdir / write-HTML sequence. One home here, so a fix to
artifact writing (permissions, parents, encoding, atomicity) lands once.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def load_state(path: str | Path) -> dict[str, Any]:
    """Read and parse a state JSON file (lenient: no schema enforcement)."""
    return json.loads(Path(path).read_text())


def _atomic_write(target: Path, text: str) -> Path:
    """Write via temp-file-then-rename so a crash mid-write can never
    leave a truncated state or dashboard behind.

    The temp file lives in the target's directory (same filesystem, so
    os.replace is atomic) and is removed on failure.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
    return target


def write_state(state: dict[str, Any], path: str | Path) -> Path:
    """Write a state file atomically. Callers are expected to have
    validated (fail-closed at write) — this function is the mechanical
    half only."""
    return _atomic_write(Path(path), json.dumps(state, indent=2) + "\n")


def render_to_file(html: str, output_path: str | Path) -> Path:
    """Write a rendered artifact atomically, creating parent directories.

    Returns the resolved path so callers can report it uniformly.
    """
    return _atomic_write(Path(output_path), html)
