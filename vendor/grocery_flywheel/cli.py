from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import analyze_state
from .importers import import_csv_history, import_normalized_history
from .model.contract import validate_canonical_state
from .render import render_dashboard
from .state_io import load_state, render_to_file, write_state


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {"import", "corrections"}:
        if argv[0] == "import":
            _run_import(argv[1:])
        else:
            _run_corrections(argv[1:])
        return

    parser = argparse.ArgumentParser(description="Render a Grocery Flywheel dashboard.")
    parser.add_argument("state", type=Path, help="Path to replenishment state JSON.")
    parser.add_argument("--output", "-o", type=Path, required=True, help="HTML output path.")
    parser.add_argument(
        "--objective", default=None,
        choices=["lowest_cost", "fewer_trips", "balanced_roi", "dietary_restrictions",
                 "allergy_safe", "best_quality", "lowest_decision_fatigue"],
        help="Rank substitutions and sourcing by this objective (opt-in; default keeps legacy ordering).",
    )
    args = parser.parse_args(argv)

    if args.output.resolve() == args.state.resolve():
        print(
            f"refusing to write HTML over the state file itself: {args.state}",
            file=sys.stderr,
        )
        raise SystemExit(2)

    state = load_state(args.state)
    analysis = analyze_state(state, objective=args.objective)
    target = render_to_file(render_dashboard(analysis), args.output)
    print(f"wrote {target}")


def _run_import(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="grocery-flywheel import",
        description="Import retailer history into a canonical state file.",
    )
    sub = parser.add_subparsers(dest="kind", required=True)

    normalized = sub.add_parser("normalized", help="Import a normalized JSON history payload.")
    normalized.add_argument("payload", type=Path)
    normalized.add_argument("--profile-id", default=None)
    normalized.add_argument("--as-of", default=None, help="Override the as_of date (ISO).")
    normalized.add_argument("--output", "-o", type=Path, required=True,
                            help="Canonical state JSON to write.")

    csv = sub.add_parser("csv", help="Import a CSV export.")
    csv.add_argument("payload", type=Path)
    csv.add_argument("--profile-id", default=None)
    csv.add_argument("--output", "-o", type=Path, required=True,
                     help="Canonical state JSON to write.")

    args = parser.parse_args(argv)

    if args.kind == "normalized":
        state = import_normalized_history(
            json.loads(args.payload.read_text()),
            profile_id=args.profile_id,
            as_of=args.as_of,
        )
    else:
        state = import_csv_history(args.payload, profile_id=args.profile_id)

    errors = validate_canonical_state(state)
    if errors:
        for error in errors:
            print(f"contract violation: {error}", file=sys.stderr)
        raise SystemExit(2)

    write_state(state, args.output)
    print(f"wrote {args.output} ({len(state['items'])} items, schema {state['schema_version']})")


def _run_corrections(argv: list[str]) -> None:
    from .corrections import SIGNAL_RULES, record_correction
    from .privacy import can_persist_correction_telemetry

    parser = argparse.ArgumentParser(
        prog="grocery-flywheel corrections",
        description="Record a durable correction signal into a state file.",
    )
    sub = parser.add_subparsers(dest="kind", required=True)
    add = sub.add_parser("add", help="Append a correction event.")
    add.add_argument("state", type=Path)
    add.add_argument("--item", required=True)
    add.add_argument("--signal", required=True, choices=sorted(SIGNAL_RULES))
    add.add_argument("--note", default="")
    args = parser.parse_args(argv)

    state = load_state(args.state)
    if not can_persist_correction_telemetry(state.get("consent")):
        print(
            "refusing to persist a correction: consent.correction_telemetry must be "
            "local_only or hosted_opt_in (local-first default is set on canonical "
            "states; legacy states need a consent object)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    record_correction(state, item=args.item, signal=args.signal, note=args.note)
    write_state(state, args.state)
    print(f"recorded {args.signal} on {args.item!r} into {args.state}")


if __name__ == "__main__":
    main()
