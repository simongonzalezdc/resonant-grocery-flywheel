"""Protocol-level coverage of the MCP stdio loop.

Pins JSON-RPC 2.0 semantics:
- id-less messages are notifications and MUST NOT get a response
- malformed JSON gets -32700
- blank lines are skipped
"""

from __future__ import annotations

import io
import json

from grocery_flywheel import __version__
from grocery_flywheel.mcp_server import serve


def _run(lines: list[str]) -> list[dict]:
    stdin = io.StringIO("".join(line + "\n" for line in lines))
    stdout = io.StringIO()
    serve(stdin, stdout)
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


def test_initialize_reports_single_sourced_version():
    replies = _run([json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
    })])
    assert len(replies) == 1
    assert replies[0]["result"]["serverInfo"]["version"] == __version__


def test_id_less_notification_gets_no_response():
    replies = _run([
        json.dumps({"jsonrpc": "2.0", "method": "tools/list"}),  # no id
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    ])
    assert len(replies) == 1
    assert replies[0]["id"] == 2


def test_malformed_json_gets_32700():
    replies = _run(["{not json"])
    assert len(replies) == 1
    assert replies[0]["error"]["code"] == -32700


def test_blank_lines_skipped():
    replies = _run(["", "   ", json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/list"})])
    assert len(replies) == 1
    assert replies[0]["id"] == 7


def test_tools_call_end_to_end():
    state = {"as_of": "2026-06-10",
             "order": {"store": "S", "date": "2026-06-01", "total": 10.0}}
    replies = _run([json.dumps({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "analyze_replenishment_state",
                   "arguments": {"state_json": json.dumps(state)}},
    })])
    assert len(replies) == 1
    text = replies[0]["result"]["content"][0]["text"]
    assert json.loads(text)["days_elapsed"] >= 1
