from __future__ import annotations

import json
import sys
from typing import Any, cast

from . import __version__
from .core import analyze_state
from .render import render_dashboard
from .state_io import load_state, render_to_file

# The MCP protocol revision this server speaks. Deliberately NOT tied to
# the package version: it tracks the protocol spec date, not releases.
PROTOCOL_VERSION = "2024-11-05"


def _load_state(args: dict[str, Any]) -> dict[str, Any]:
    state_json = args.get("state_json")
    state_path = args.get("state_path")
    if state_json:
        return cast(dict[str, Any], json.loads(str(state_json)))
    if state_path:
        return load_state(str(state_path))
    raise ValueError("Provide state_json or state_path.")


def analyze_replenishment_state(args: dict[str, Any]) -> dict[str, Any]:
    return analyze_state(_load_state(args))


def render_replenishment_dashboard(args: dict[str, Any]) -> dict[str, Any]:
    output_path = args.get("output_path")
    if not output_path:
        raise ValueError("Provide output_path.")
    analysis = analyze_state(_load_state(args))
    target = render_to_file(render_dashboard(analysis), str(output_path))
    return {"output_path": str(target), "items": len(analysis["items"])}


def summarize_sourcing_research(args: dict[str, Any]) -> dict[str, Any]:
    analysis = analyze_state(_load_state(args))
    rows = analysis.get("sourcing_research", [])
    return {
        "count": len(rows),
        "items": [
            {
                "item": row.get("item"),
                "current_source": row.get("current_source"),
                "research_question": row.get("research_question"),
                "decision_boundary": row.get("decision_boundary"),
            }
            for row in rows
        ],
    }


def evaluate_dietary(args: dict[str, Any]) -> dict[str, Any]:
    analysis = analyze_state(_load_state(args), objective=args.get("objective"))
    evaluations = analysis.get("dietary_evaluations", [])
    by_result: dict[str, int] = {}
    for row in evaluations:
        by_result[row["result"]] = by_result.get(row["result"], 0) + 1
    return {
        "objective": analysis.get("objective"),
        "counts_by_result": by_result,
        "evaluations": [
            {
                "item": row["item"],
                "profile_id": row["profile_id"],
                "restriction": row["restriction"],
                "result": row["result"],
                "safety_tier": row["safety_tier"],
                "evidence_status": row["evidence_status"],
                "reason": row["reason"],
            }
            for row in evaluations
        ],
    }


def plan_next_cart(args: dict[str, Any]) -> dict[str, Any]:
    from .draft import generate_cart_plan

    analysis = analyze_state(_load_state(args), objective=args.get("objective"))
    plan = generate_cart_plan(analysis, mode=str(args.get("mode", "pickup")))
    # Structural approval boundary: this server plans, a human decides.
    # There is no checkout surface, and there never will be one here.
    # RuntimeError (not assert) so the guarantee survives python -O.
    if plan.get("checkout_available") is not False:
        raise RuntimeError("approval boundary violated: checkout_available must be false")
    if plan.get("approval_required") is not True:
        raise RuntimeError("approval boundary violated: approval_required must be true")
    if any(item.get("approval_state") != "needs_human_approval" for item in plan["items"]):
        raise RuntimeError("approval boundary violated: every item needs human approval")
    return {
        "mode": plan["mode"],
        "approval_required": plan["approval_required"],
        "checkout_available": plan["checkout_available"],
        "item_count": len(plan["items"]),
        "items": plan["items"],
    }


ToolSpec = dict[str, Any]

TOOLS: dict[str, ToolSpec] = {
    "analyze_replenishment_state": {
        "description": "Analyze a Grocery Flywheel replenishment state document and return its structured analysis (items, gaps, sourcing research). Returns a state analysis dict. Use when the agent needs the replenishment picture before rendering or summarizing. Pass state_json (inline state) or state_path (path to a state file) from user input or a previous step.",
        "handler": analyze_replenishment_state,
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_path": {"type": "string"},
                "state_json": {"type": "string"},
            },
        },
    },
    "render_replenishment_dashboard": {
        "description": "Render the Grocery Flywheel replenishment dashboard as a self-contained HTML file on disk. Returns a dict with output_path (the written file) and items (analyzed item count). Use when the agent must produce a viewable dashboard artifact. Pass output_path (the HTML target) plus state_json or state_path from a prior analyze_replenishment_state result or user input.",
        "handler": render_replenishment_dashboard,
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_path": {"type": "string"},
                "state_json": {"type": "string"},
                "output_path": {"type": "string"},
            },
            "required": ["output_path"],
        },
    },
    "summarize_sourcing_research": {
        "description": "Extract sourcing research questions and decision boundaries from a replenishment state document. Returns a dict with count and items (item, current_source, research_question, decision_boundary). Use when the agent must summarize open sourcing decisions without the full analysis. Pass state_json or state_path from a prior analyze_replenishment_state result or user input.",
        "handler": summarize_sourcing_research,
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_path": {"type": "string"},
                "state_json": {"type": "string"},
            },
        },
    },
    "evaluate_dietary": {
        "description": "Evaluate every item against the state's dietary restriction profiles using evidence-gated, fail-closed safety logic (safety-critical restrictions without label evidence return needs_review, never safe). Returns counts_by_result and per-item evaluations (item, restriction, result, safety_tier, evidence_status, reason). Optionally pass objective (one of: lowest_cost, fewer_trips, balanced_roi, dietary_restrictions, allergy_safe, best_quality, lowest_decision_fatigue) to also apply objective-aware ranking. Use when the agent must check dietary safety or explain why an item was flagged.",
        "handler": evaluate_dietary,
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_path": {"type": "string"},
                "state_json": {"type": "string"},
                "objective": {"type": "string"},
            },
        },
    },
    "plan_next_cart": {
        "description": "Generate an internal next-cart plan from a replenishment state: restock candidates from observed depletion plus sourcing moves, each marked needs_human_approval. The result is a plan for a human to act on — checkout_available is always false and the server asserts it; this tool never places orders or touches a retailer cart. Optionally pass objective and mode (pickup, delivery, in_person). Use when the agent must propose the next cart for user review.",
        "handler": plan_next_cart,
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_path": {"type": "string"},
                "state_json": {"type": "string"},
                "objective": {"type": "string"},
                "mode": {"type": "string", "enum": ["pickup", "delivery", "in_person"]},
            },
        },
    },
}


def handle_tool_call(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if name not in TOOLS:
        raise ValueError(f"Unknown tool: {name}")
    if arguments is not None and not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    handler = TOOLS[name]["handler"]
    return cast(dict[str, Any], handler(arguments or {}))


def _tool_list() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": spec["description"],
            "inputSchema": spec["inputSchema"],
        }
        for name, spec in sorted(TOOLS.items())
    ]


def _response(message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    message_id = message.get("id")
    has_id = "id" in message
    params = message.get("params") or {}

    # JSON-RPC 2.0: a notification is a request WITHOUT an id key. An
    # explicit "id": null is (discouraged but) a request and gets a reply.
    if not has_id:
        return None
    if message.get("jsonrpc") not in (None, "2.0"):
        return _error(message_id, -32600, f"Invalid jsonrpc version: {message.get('jsonrpc')!r}")
    if not isinstance(message_id, (str, int, float)) and message_id is not None:
        return _error(None, -32600, "id must be a string, number, or null")
    if method is None:
        return _error(message_id, -32600, "Missing method")
    if method == "initialize":
        return _response(
            message_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "grocery-flywheel", "version": __version__},
            },
        )
    if method == "tools/list":
        return _response(
            message_id,
            {
                "tools": _tool_list(),
                "_meta": {"ttlMs": 3600000, "cacheScope": "public"},
            },
        )
    if method == "tools/call":
        try:
            result = handle_tool_call(params.get("name", ""), params.get("arguments") or {})
            return _response(
                message_id,
                {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
            )
        except ValueError as exc:
            return _error(message_id, -32602, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _error(message_id, -32603, f"Internal error: {exc}")
    return _error(message_id, -32601, f"Unsupported method: {method}")


# A single request line larger than this is rejected before parsing —
# unbounded reads let a hostile client OOM the server (QA finding).
MAX_LINE_BYTES = 16 * 1024 * 1024


def serve(stdin: Any, stdout: Any) -> None:
    """Run the line-delimited JSON-RPC loop over the given streams.

    Split from ``main`` so tests can drive the protocol with StringIO
    instead of the real stdin/stdout.
    """
    while True:
        line = stdin.readline()
        if not line:
            break
        if not line.strip():
            continue
        if len(line) > MAX_LINE_BYTES:
            reply = _error(None, -32600, f"Request line exceeds {MAX_LINE_BYTES} bytes")
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
            continue
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                reply = _error(None, -32600, "Invalid Request: expected a single object")
            else:
                reply = handle_message(message)
        except json.JSONDecodeError as exc:
            reply = _error(None, -32700, f"Invalid JSON: {exc}")
        except RecursionError:
            reply = _error(None, -32600, "Invalid Request: nesting too deep")
        except Exception as exc:  # noqa: BLE001
            reply = _error(None, -32603, f"Internal error: {exc}")
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()


def main() -> None:
    serve(sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
