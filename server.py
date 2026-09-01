#!/usr/bin/env python3
"""addon.grocery-flywheel local-service entry (http-json on 127.0.0.1:4899).

ResonantOS add-on contract: protocol http-json, healthCommand groceryflywheel.status.
Wraps the FROZEN vendored grocery_flywheel package in-process (no subprocess,
no shell, no secrets on argv) and exposes the same verbs the upstream MCP
server exposes: analyze, dietary, sourcing, plan, plus the dashboard render.
The plan verb inherits upstream's structural approval boundary: the vendored
plan_next_cart raises unless checkout_available is false, approval_required is
true, and every item is needs_human_approval. Nothing here orders anything.

Containment boundary (declared deviation from the upstream MCP surface):
state_path and output_path are NOT accepted. State arrives inline as
state_json only, and dashboard HTML is written only under <addon>/var/
dashboards/. No filesystem capability exists; nothing leaves the machine.

All responses and everything persisted under var/ pass through home-path
redaction (food/habit data is personal; it stays local and stays un-pathed).

Exit codes: 0 normal stop; 78 port bind failure.
"""

import json
import os
import re
import socket
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import grocery_flywheel  # noqa: E402  (vendored, byte-identical, hash-pinned by tests)
from grocery_flywheel import mcp_server  # noqa: E402  (the REAL upstream tool surface)
from grocery_flywheel.core import analyze_state  # noqa: E402
from grocery_flywheel.optimization import OBJECTIVES  # noqa: E402
from grocery_flywheel.render import render_dashboard  # noqa: E402

PORT = int(os.environ.get("GROCERYFLYWHEEL_PORT", "4899"))  # dev override; manifest port 4899 is the contract
MAX_BODY = 64 * 1024
MAX_STR = 2048
MAX_STATE_CHARS = 60000  # leaves room for the envelope inside a 64KB body
FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MODES = ("pickup", "delivery", "in_person")
OBJECTIVE_ENUM = sorted(OBJECTIVES)  # sourced from the vendored engine, never hand-maintained

ADDON_ROOT = os.path.dirname(os.path.abspath(__file__))
DASH_BASE = os.path.join(ADDON_ROOT, "var", "dashboards")

# Per-method param allowlists (checkyourself style). state_path and
# output_path are deliberately absent: no arbitrary filesystem IO here.
PER_METHOD_FIELDS = {
    "groceryflywheel.analyze": {"state_json", "objective"},
    "groceryflywheel.dietary": {"state_json", "objective"},
    "groceryflywheel.sourcing": {"state_json"},  # upstream summarize tool ignores objective; no no-op params
    "groceryflywheel.plan": {"state_json", "objective", "mode"},
    "groceryflywheel.dashboard": {"state_json", "objective", "filename"},
}

# Methods handled by the vendored upstream MCP tool handlers, keyed by the
# service verb. The dashboard verb is composed below (confined write).
MCP_TOOL_FOR = {
    "groceryflywheel.analyze": "analyze_replenishment_state",
    "groceryflywheel.dietary": "evaluate_dietary",
    "groceryflywheel.sourcing": "summarize_sourcing_research",
    "groceryflywheel.plan": "plan_next_cart",
}

_state = {
    "busy": False,
    "last_dashboard": None,
}
_lock = threading.Lock()


def _check_string(name, value, max_len=MAX_STR):
    if not isinstance(value, str) or not (0 < len(value) <= max_len):
        return f"{name} must be a non-empty string of at most {max_len} characters"
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        return f"{name} contains control characters"
    return None


def _parse_state(value):
    """Validate + parse state_json. Returns (state dict, error string).

    json.loads is the control-character validator for the state TEXT: raw
    control characters inside JSON strings are invalid JSON (rejected here),
    while whitespace between tokens is legal JSON. Enum/string params use the
    explicit _check_string scan instead.
    """
    err = (None if isinstance(value, str) else "state_json must be a string")
    if err is None and not (0 < len(value) <= MAX_STATE_CHARS):
        err = f"state_json must be a non-empty string of at most {MAX_STATE_CHARS} characters"
    if err:
        return None, err
    try:
        state = json.loads(value)
    except (ValueError, UnicodeDecodeError) as exc:
        return None, f"state_json is not valid JSON: {exc}"[:300]
    if not isinstance(state, dict):
        return None, "state_json must decode to a JSON object"
    return state, None


def _validate_params(method, params):
    """Service-boundary validation. Returns upstream-argument dict or an error string.

    Anything not rejected here is handed to the vendored module, whose own
    ValueError contract (the same one its MCP server surfaces) becomes a 400.
    """
    if not isinstance(params, dict):
        return None, "params must be an object"
    allowed = PER_METHOD_FIELDS.get(method)
    if allowed is None:
        return None, f"unknown method: {method}"
    for key in params:
        if key not in allowed:
            return None, f"unknown field: {key}"

    state, err = _parse_state(params.get("state_json"))
    if err:
        return None, err
    args = {"state_json": params["state_json"]}

    objective = params.get("objective")
    if objective is not None:
        err = _check_string("objective", objective)
        if err:
            return None, err
        if objective not in OBJECTIVES:
            return None, f"unknown objective: {objective}"
        args["objective"] = objective

    if method == "groceryflywheel.plan":
        mode = params.get("mode", "pickup")
        err = _check_string("mode", mode)
        if err:
            return None, err
        if mode not in MODES:
            return None, "mode must be one of: pickup, delivery, in_person"
        args["mode"] = mode

    if method == "groceryflywheel.dashboard":
        filename = params.get("filename")
        if filename is None:
            filename = "dashboard-" + uuid.uuid4().hex[:8] + ".html"
        err = _check_string("filename", filename, max_len=80)
        if err:
            return None, err
        if not FILENAME_RE.match(filename):
            return None, "filename may only contain ASCII letters, digits, dot, underscore, hyphen (no paths)"
        if not filename.endswith(".html"):
            filename += ".html"
        args["_filename"] = filename

    return args, None


def _redact_text(text):
    home = os.path.expanduser("~")
    return text.replace(home, "~") if home and home != "~" else text


def _redact_obj(obj):
    if isinstance(obj, str):
        return _redact_text(obj)
    if isinstance(obj, list):
        return [_redact_obj(item) for item in obj]
    if isinstance(obj, dict):
        return {key: _redact_obj(value) for key, value in obj.items()}
    return obj


def _run_dashboard(args):
    """Render the dashboard under var/dashboards/ (single-flight). Returns (payload, status).

    Uses the same analyze_state + render_dashboard composition as the upstream
    render tool, but the write target is confined to this addon's var/ tree and
    the HTML is home-path-redacted BEFORE it ever touches disk.
    """
    with _lock:
        if _state["busy"]:
            return {"error": "a dashboard render is already in progress", "last_dashboard": _state["last_dashboard"]}, 409
        _state["busy"] = True
    try:
        state, err = _parse_state(args["state_json"])
        if err:  # unreachable via _validate_params; kept as an honest guard
            return {"error": err}, 400
        objective = args.get("objective")
        analysis = analyze_state(state, objective=objective)
        html = _redact_text(render_dashboard(analysis))
        target = os.path.join(DASH_BASE, args["_filename"])
        os.makedirs(DASH_BASE, exist_ok=True)
        with open(target, "w") as f:  # filename is regex-confined to one path segment
            f.write(html)
        rel = os.path.relpath(target, ADDON_ROOT)
        with _lock:
            _state["last_dashboard"] = rel
        # Same response shape as upstream's render_replenishment_dashboard.
        return _redact_obj({"output_path": rel, "items": len(analysis["items"])}), 200
    except (ValueError, KeyError, TypeError) as exc:  # invalid state = caller's problem
        return _redact_obj({"error": _engine_error(exc)}), 400
    except Exception as exc:  # honest failure, never a server crash
        return _redact_obj({"error": "dashboard render failed: " + str(exc)[:300]}), 500
    finally:
        with _lock:
            _state["busy"] = False


def _engine_error(exc):
    if isinstance(exc, KeyError):
        return f"invalid state: missing required field {exc}"
    return f"invalid state: {exc}"[:300]


def _run_mcp_tool(verb, args):
    """Run one vendored upstream MCP tool handler. Returns (payload, status)."""
    try:
        result = mcp_server.handle_tool_call(MCP_TOOL_FOR[verb], args)
        return _redact_obj(result), 200
    except (ValueError, KeyError, TypeError) as exc:  # invalid state = caller's problem
        return _redact_obj({"error": _engine_error(exc)}), 400
    except RuntimeError as exc:  # upstream approval-boundary assertion: never paper over
        return _redact_obj({"error": "approval boundary violated: " + str(exc)[:200]}), 500
    except Exception as exc:  # honest failure, never a server crash
        return _redact_obj({"error": "tool failed: " + str(exc)[:300]}), 500


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 30  # a lying Content-Length must not pin a thread forever

    def _reply(self, code, payload, close=False):
        if close:
            self.close_connection = True  # never leave undrained bodies on a keep-alive connection
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/health"):
            self._reply(200, self._status())
        else:
            self._reply(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/":
            self._reply(404, {"error": "not found"}, close=True)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._reply(400, {"error": "bad content-length"}, close=True)
            return
        if length <= 0 or length > MAX_BODY:
            self._reply(413 if length > MAX_BODY else 400, {"error": "body must be 1..65536 bytes"}, close=True)
            return
        try:
            req = json.loads(self.rfile.read(length).decode("utf-8"))
        except (TimeoutError, socket.timeout, OSError):
            self._reply(408, {"error": "request body incomplete (timeout)"}, close=True)
            return
        except (ValueError, UnicodeDecodeError):
            self._reply(400, {"error": "body must be valid JSON"}, close=True)
            return
        if not isinstance(req, dict):
            self._reply(400, {"error": "body must be a JSON object"}, close=True)
            return
        method = req.get("method")
        params = req.get("params", {})
        for key in req:
            if key not in ("method", "params"):
                self._reply(400, {"error": f"unknown field: {key}"}, close=True)
                return
        if method == "groceryflywheel.status":
            self._reply(200, self._status())
            return
        args, err = _validate_params(method if isinstance(method, str) else "", params)
        if err:
            # review finding R2: error echoes pass through redaction like every
            # other response. R1: `method in PER_METHOD_FIELDS` on a non-string
            # method (e.g. a JSON array) would raise TypeError (unhashable), so
            # membership is guarded by isinstance.
            known = isinstance(method, str) and method in PER_METHOD_FIELDS
            self._reply(400 if known else 404, {"error": _redact_text(err)})
            return
        if method == "groceryflywheel.dashboard":
            payload, code = _run_dashboard(args)
            self._reply(code, payload)
            return
        payload, code = _run_mcp_tool(method, args)
        self._reply(code, payload)

    def _status(self):
        with _lock:
            return {
                "ok": True,
                "tool": "grocery-flywheel",
                "version": grocery_flywheel.__version__,
                "busy": _state["busy"],
                "last_dashboard": _state["last_dashboard"],
            }

    def log_message(self, fmt, *args):  # keep service logs quiet and content-free
        sys.stderr.write("groceryflywheel-service: " + (fmt % args) + "\n")


def main():
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as exc:
        sys.stderr.write(f"groceryflywheel-service: cannot bind 127.0.0.1:{PORT} ({exc}); manifest entrypoint expects this port\n")
        return 78
    sys.stderr.write(f"groceryflywheel-service: listening on http://127.0.0.1:{PORT}\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
