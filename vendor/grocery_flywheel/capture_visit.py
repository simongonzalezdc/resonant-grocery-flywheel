"""grocery_flywheel.capture_visit — small CLI to log a trip into the state.

Kept separate from the dashboard CLI so the public package stays minimal.
The user runs::

    grocery-flywheel-capture-visit path/to/state.json \\
        --type in_store --started-at 2026-06-07T10:00 --duration-min 45

The state file is loaded, the visit is appended, and the file is written
back. No external side effects.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .cost_log import VALID_VISIT_TYPES, add_visit
from .state_io import load_state, write_state


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Log a trip (in-store, pickup, or delivery) into a state file.",
    )
    parser.add_argument("state", type=Path, help="Path to replenishment state JSON.")
    parser.add_argument(
        "--type", required=True, choices=sorted(VALID_VISIT_TYPES),
        help="Type of visit.",
    )
    parser.add_argument(
        "--started-at", required=True,
        help="ISO timestamp (e.g. 2026-06-07T10:00) the visit started.",
    )
    parser.add_argument(
        "--duration-min", required=True, type=int,
        help="Length of the visit in minutes.",
    )
    parser.add_argument(
        "--notes", default="", help="Optional free-text notes.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    state = load_state(args.state)
    visit = add_visit(
        state,
        visit_type=args.type,
        started_at=args.started_at,
        duration_min=args.duration_min,
        notes=args.notes,
    )
    # Atomic write via the shared IO home (also keeps the trailing
    # newline consistent with every other state writer).
    write_state(state, args.state)
    print(f"logged visit {visit['id']} ({visit['visit_type']}, {visit['duration_min']} min)")


if __name__ == "__main__":
    main()
