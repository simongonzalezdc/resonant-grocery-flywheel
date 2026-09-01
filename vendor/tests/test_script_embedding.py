"""Regression: JSON embedded inside <script> blocks must not be escapable.

An item name containing ``</script><script>...`` used to break out of the
correction-capture payload and execute attacker JS when the dashboard was
opened (found by adversarial QA, 2026-08-14). The fix escapes ``<`` (and
line separators) in embedded JSON so a script block can never be closed
by data.
"""

from __future__ import annotations

from grocery_flywheel.core import analyze_state
from grocery_flywheel.rendering import render_dashboard

_CONSENT = {"correction_telemetry": "local_only", "hosted_sync": False,
            "retailer_session_storage": "none", "password_storage": "forbidden"}

_STATE = {
    "as_of": "2026-06-10",
    "order": {"store": "S", "date": "2026-06-01", "total": 5.0},
    "consent": _CONSENT,  # consent present → correction capture panel renders
}


def test_item_name_cannot_break_out_of_script_block():
    state = dict(_STATE)
    state["items"] = [{"name": "</script><script>alert('pwned')//", "spend": 1.0}]
    html = render_dashboard(analyze_state(state))
    assert "</script><script>" not in html
    # the payload must carry the name only in escaped, inert form
    assert "\\u003c/script\\u003e" in html
    # and it must still decode back to the original data (round-trip)
    import json as _json
    import re as _re
    payload = _re.search(r"var _state = (.*?);\n", html).group(1)
    assert _json.loads(payload) == {"items": ["</script><script>alert('pwned')//"]}


def test_payload_survives_unicode_line_separators():
    state = dict(_STATE)
    state["items"] = [{"name": "evil" + chr(0x2028) + "linesep" + chr(0x2029), "spend": 1.0}]
    html = render_dashboard(analyze_state(state))
    script_block = html.split("<script>")[1].split("</script>")[0]
    assert chr(0x2028) not in script_block and chr(0x2029) not in script_block


def test_body_panels_still_escape_html():
    state = dict(_STATE)
    state["items"] = [{"name": "<img src=x onerror=alert(1)>", "spend": 1.0}]
    html = render_dashboard(analyze_state(state))
    # The markup region (everything outside script blocks) must have the
    # tag defused — escaped entities, never a live <img element.
    markup = html.split("<script>")[0] + html.rsplit("</script>", 1)[-1]
    assert "<img src=x" not in markup
    assert "&lt;img src=x" in markup
