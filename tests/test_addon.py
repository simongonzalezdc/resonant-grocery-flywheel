"""addon.grocery-flywheel wrapper tests.

Run:  python3 -m unittest discover -s tests -v   (from the add-on root)

Pins: vendor byte-identity vs upstream, manifest/service parity, the live
engine verbs (analyze / dietary / sourcing / plan / dashboard), the structural
approval boundary, home-path redaction on responses AND disk, and the live
adversarial matrix. Only synthetic fixtures and the upstream sanitized example
are used — never real food or habit data.
"""
import hashlib
import http.client
import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON_ROOT = os.path.dirname(HERE)
UPSTREAM = os.path.expanduser("~/workspaces/grocery-flywheel")
sys.path.insert(0, ADDON_ROOT)
sys.path.insert(0, os.path.join(ADDON_ROOT, "vendor"))

import server  # noqa: E402
import grocery_flywheel  # noqa: E402
from grocery_flywheel import mcp_server  # noqa: E402

TEST_PORT = 5899  # never 4899: that is the live service contract port
BASE = f"http://127.0.0.1:{TEST_PORT}"

SAMPLE_STATE_TEXT = open(
    os.path.join(ADDON_ROOT, "vendor", "examples", "sample_state.json")
).read()


def post(payload, raw=None):
    body = raw if raw is not None else json.dumps(payload).encode()
    req = urllib.request.Request(BASE + "/", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode())


def post_err(payload, raw=None):
    try:
        return post(payload, raw)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def make_state(items=None, profiles=None):
    """A minimal valid synthetic state (analyze_state needs order + as_of)."""
    return {
        "as_of": "2026-05-24",
        "order": {"date": "2026-05-10", "total": 40.0, "store": "Neighborhood Co-op"},
        "items": items if items is not None else [
            {
                "name": "Oat milk",
                "role": "staple",
                "category": "dairy_alt",
                "storage": "fridge",
                "spend": 4.0,
                "units_total": 4,
                "units_remaining": 0,
                "pricing_status": "priced",
            },
        ],
        "dietary_profiles": profiles or [],
    }


ALLERGY_PROFILE = {
    "profile_id": "allergy",
    "restrictions": [
        {
            "type": "food_allergy",
            "value": "peanuts",
            "safety_tier": "safety_critical",
            "behavior": "block_until_review",
        }
    ],
}


class Service:
    def __enter__(self):
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", TEST_PORT), server.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        server._state.update({"busy": False, "last_dashboard": None})


class TestVendorPin(unittest.TestCase):
    """Every vendored file is byte-identical to upstream HEAD."""

    def test_vendored_files_hash_identical_to_upstream(self):
        checked = 0
        for sub, upstream_sub in (
            ("grocery_flywheel", os.path.join("src", "grocery_flywheel")),
            ("tests", "tests"),
            ("examples", "examples"),
        ):
            vendored_root = os.path.join(ADDON_ROOT, "vendor", sub)
            for root, dirs, files in os.walk(vendored_root):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for name in files:
                    if name.endswith((".pyc", ".DS_Store")):
                        continue
                    ours = os.path.join(root, name)
                    rel = os.path.relpath(ours, os.path.join(ADDON_ROOT, "vendor", sub))
                    theirs = os.path.join(UPSTREAM, upstream_sub, rel)
                    self.assertTrue(os.path.exists(theirs), f"upstream missing: {rel}")
                    self.assertEqual(sha256(ours), sha256(theirs), f"vendor drift: {rel}")
                    checked += 1
        self.assertGreater(checked, 40, "vendor pin walked suspiciously few files")

    def test_upstream_head_matches_pinned_commit(self):
        import subprocess
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=UPSTREAM, capture_output=True, text=True, check=True
        ).stdout.strip()
        self.assertTrue(head.startswith("82da650"), f"upstream moved past pinned HEAD: {head}")


class TestManifestParity(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ADDON_ROOT, "addon.json")) as f:
            self.manifest = json.load(f)

    def test_tool_names_match_service_methods(self):
        names = {t["name"] for t in self.manifest["tools"]}
        self.assertEqual(names, set(server.PER_METHOD_FIELDS) | {"groceryflywheel.status"})

    def test_zero_capability_posture(self):
        self.assertEqual(self.manifest["requestedCapabilities"], [])
        for tool in self.manifest["tools"]:
            self.assertEqual(tool["requiredCapabilities"], [], tool["name"])

    def test_objective_enum_matches_engine(self):
        for tool in self.manifest["tools"]:
            enum = tool.get("inputSchema", {}).get("properties", {}).get("objective", {}).get("enum")
            if enum is not None:
                self.assertEqual(enum, server.OBJECTIVE_ENUM, tool["name"])

    def test_entrypoint_port_and_health_command(self):
        entry = self.manifest["service"]["entrypoint"]
        self.assertTrue(entry.endswith(":4899"), entry)
        self.assertEqual(server.PORT, 4899)
        self.assertEqual(self.manifest["service"]["healthCommand"], "groceryflywheel.status")
        self.assertEqual(self.manifest["service"]["protocol"], "http-json")


class TestInternalApiPin(unittest.TestCase):
    def test_upstream_mcp_surface_covers_every_mapped_verb(self):
        self.assertTrue(set(server.MCP_TOOL_FOR.values()).issubset(mcp_server.TOOLS))

    def test_engine_version(self):
        self.assertEqual(grocery_flywheel.__version__, "0.2.0")

    def test_engine_plan_boundary_is_structural(self):
        result = mcp_server.handle_tool_call("plan_next_cart", {"state_json": json.dumps(make_state())})
        self.assertIs(result["checkout_available"], False)
        self.assertIs(result["approval_required"], True)


class TestStatus(unittest.TestCase):
    def test_status_roundtrip(self):
        with Service():
            code, body = post({"method": "groceryflywheel.status"})
            self.assertEqual(code, 200)
            self.assertTrue(body["ok"])
            self.assertEqual(body["tool"], "grocery-flywheel")
            self.assertEqual(body["version"], grocery_flywheel.__version__)
            self.assertFalse(body["busy"])
            self.assertIsNone(body["last_dashboard"])

    def test_get_health(self):
        with Service():
            with urllib.request.urlopen(BASE + "/health", timeout=10) as resp:
                body = json.loads(resp.read().decode())
            self.assertTrue(body["ok"])

    def test_get_unknown_path_404(self):
        with Service():
            try:
                urllib.request.urlopen(BASE + "/nope", timeout=10)
                self.fail("expected 404")
            except urllib.error.HTTPError as exc:
                self.assertEqual(exc.code, 404)


class TestEngineVerbs(unittest.TestCase):
    def test_analyze_full_sample_state(self):
        with Service():
            code, body = post({"method": "groceryflywheel.analyze", "params": {"state_json": SAMPLE_STATE_TEXT}})
            self.assertEqual(code, 200)
            self.assertEqual(len(body["items"]), 13)
            for key in ("estimated_total_days", "known_consumed_fraction", "dietary_evaluations",
                        "sourcing_research", "first_wow", "cart_plan"):
                self.assertIn(key, body)

    def test_analyze_objective_quirk_preserved_and_declared(self):
        # Upstream's analyze_replenishment_state handler advertises objective
        # in its MCP schema but does not pass it through (only dietary and
        # plan do). The wrapper preserves upstream behavior exactly; set
        # state["objective"] for an objective-aware analyze instead.
        with Service():
            code, body = post({"method": "groceryflywheel.analyze", "params": {
                "state_json": SAMPLE_STATE_TEXT, "objective": "lowest_cost"}})
            self.assertEqual(code, 200)
            self.assertIsNone(body["objective"])
            # the same state IS objective-aware when the state carries it
            state = json.loads(SAMPLE_STATE_TEXT)
            state["objective"] = "lowest_cost"
            code, body = post({"method": "groceryflywheel.analyze", "params": {
                "state_json": json.dumps(state)}})
            self.assertEqual(code, 200)
            self.assertEqual(body["objective"], "lowest_cost")
            self.assertEqual(body["objective_label"], "Lowest cost")

    def test_dietary_fail_closed_without_evidence(self):
        state = make_state(
            items=[{"name": "Mystery snack", "spend": 2.0, "product_evidence": []}],
            profiles=[ALLERGY_PROFILE],
        )
        with Service():
            code, body = post({"method": "groceryflywheel.dietary", "params": {"state_json": json.dumps(state)}})
            self.assertEqual(code, 200)
            self.assertGreaterEqual(body["counts_by_result"].get("needs_review", 0), 1)
            row = [e for e in body["evaluations"] if e["item"] == "Mystery snack"][0]
            self.assertEqual(row["result"], "needs_review")
            self.assertEqual(row["evidence_status"], "missing")

    def test_sourcing_shape(self):
        with Service():
            code, body = post({"method": "groceryflywheel.sourcing", "params": {"state_json": SAMPLE_STATE_TEXT}})
            self.assertEqual(code, 200)
            self.assertGreaterEqual(body["count"], 1)
            self.assertEqual(body["count"], len(body["items"]))
            for row in body["items"]:
                for key in ("item", "current_source", "research_question", "decision_boundary"):
                    self.assertIn(key, row)

    def test_plan_always_waits_for_human_approval(self):
        with Service():
            code, body = post({"method": "groceryflywheel.plan", "params": {
                "state_json": SAMPLE_STATE_TEXT, "mode": "delivery", "objective": "allergy_safe"}})
            self.assertEqual(code, 200)
            self.assertEqual(body["mode"], "delivery")
            self.assertIs(body["checkout_available"], False)
            self.assertIs(body["approval_required"], True)
            self.assertEqual(body["item_count"], len(body["items"]))
            for item in body["items"]:
                self.assertEqual(item["approval_state"], "needs_human_approval")

    def test_dashboard_written_under_var(self):
        with Service():
            code, body = post({"method": "groceryflywheel.dashboard", "params": {
                "state_json": SAMPLE_STATE_TEXT, "filename": "gate-check"}})
            self.assertEqual(code, 200)
            self.assertEqual(body["items"], 13)
            self.assertTrue(body["output_path"].startswith("var/dashboards/"))
            self.assertTrue(body["output_path"].endswith("gate-check.html"))
            with open(os.path.join(ADDON_ROOT, body["output_path"])) as f:
                html = f.read()
            self.assertIn("<", html)
            self.assertIn("gate-check.html", json.dumps(body))

    def test_dashboard_autogenerated_filename(self):
        with Service():
            code, body = post({"method": "groceryflywheel.dashboard", "params": {"state_json": SAMPLE_STATE_TEXT}})
            self.assertEqual(code, 200)
            self.assertTrue(body["output_path"].startswith("var/dashboards/dashboard-"))
            self.assertTrue(os.path.exists(os.path.join(ADDON_ROOT, body["output_path"])))


class TestAdversarialMatrix(unittest.TestCase):
    """The live 8/8 adversarial matrix against a running service."""

    def test_1_unknown_method_404(self):
        with Service():
            code, _ = post_err({"method": "groceryflywheel.checkout", "params": {"state_json": "{}"}})
            self.assertEqual(code, 404)

    def test_2_unknown_envelope_field_400(self):
        with Service():
            code, _ = post_err({"method": "groceryflywheel.status", "params": {}, "checkout": True})
            self.assertEqual(code, 400)

    def test_2b_non_string_method_no_crash(self):
        # review R1: an unhashable JSON method value must 404, never TypeError
        with Service():
            for bad_method in (["groceryflywheel.analyze"], {"m": 1}, 42, None):
                code, _ = post_err({"method": bad_method, "params": {}})
                self.assertEqual(code, 404, bad_method)

    def test_2c_error_echoes_redacted(self):
        # review R2: even validation error echoes pass through redaction
        home = os.path.expanduser("~")
        with Service():
            code, body = post_err({"method": "groceryflywheel.analyze", "params": {
                "state_json": SAMPLE_STATE_TEXT, "objective": "lowest_cost " + home}})
            self.assertEqual(code, 400)
            self.assertNotIn(home, json.dumps(body))
            self.assertIn("~", body["error"])

    def test_3_dropped_path_params_refused(self):
        with Service():
            for params in (
                {"state_json": SAMPLE_STATE_TEXT, "state_path": "/etc/passwd"},
                {"state_json": SAMPLE_STATE_TEXT, "output_path": "/tmp/evil.html"},
            ):
                code, body = post_err({"method": "groceryflywheel.analyze", "params": params})
                self.assertEqual(code, 400, params)

    def test_4_control_characters_rejected(self):
        with Service():
            for params in (
                {"state_json": SAMPLE_STATE_TEXT, "objective": "lowest\x00cost"},
                {"state_json": SAMPLE_STATE_TEXT, "objective": "lowest\ncost"},
                {"state_json": SAMPLE_STATE_TEXT, "filename": "bad\nname.html"},
            ):
                code, _ = post_err({"method": "groceryflywheel.analyze" if "filename" not in params else "groceryflywheel.dashboard", "params": params})
                self.assertEqual(code, 400, params)

    def test_5_path_traversal_filename_rejected(self):
        with Service():
            for name in ("../evil", "a/b", "..", ".hidden", "sub\\dir"):
                code, _ = post_err({"method": "groceryflywheel.dashboard", "params": {
                    "state_json": SAMPLE_STATE_TEXT, "filename": name}})
                self.assertEqual(code, 400, name)

    def test_6_oversized_body_413(self):
        with Service():
            state_json = json.dumps(make_state()) + " " + ("x" * (server.MAX_BODY + 1024))
            raw = json.dumps({"method": "groceryflywheel.analyze", "params": {"state_json": state_json}}).encode()
            self.assertGreater(len(raw), server.MAX_BODY)
            code, _ = post_err(None, raw=raw)
            self.assertEqual(code, 413)

    def test_7_malformed_requests_400(self):
        with Service():
            code, _ = post_err(None, raw=b"{not json")
            self.assertEqual(code, 400)
            conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=10)
            try:
                conn.putrequest("POST", "/")
                conn.putheader("Content-Length", "not-a-number")
                conn.endheaders()
                resp = conn.getresponse()
                self.assertEqual(resp.status, 400)
                resp.read()
            finally:
                conn.close()
            code, _ = post_err(None, raw=b"")
            self.assertIn(code, (400, 413))  # zero body is refused either way

    def test_8_invalid_state_is_honest_400(self):
        with Service():
            bad_states = (
                json.dumps({"as_of": "2026-05-24"}),                       # missing order
                json.dumps({"order": {"date": "2026-05-10", "total": 10}, "as_of": "not-a-date"}),
                "not json at all",
                json.dumps([1, 2, 3]),                                     # not an object
            )
            for state in bad_states:
                code, body = post_err({"method": "groceryflywheel.analyze", "params": {"state_json": state}})
                self.assertEqual(code, 400, state[:40])
                self.assertIn("error", body)
            code, body = post_err({"method": "groceryflywheel.plan", "params": {
                "state_json": SAMPLE_STATE_TEXT, "mode": "teleport"}})
            self.assertEqual(code, 400)
            code, _ = post_err({"method": "groceryflywheel.analyze", "params": {
                "state_json": SAMPLE_STATE_TEXT, "objective": "shiniest_stuff"}})
            self.assertEqual(code, 400)


class TestRedaction(unittest.TestCase):
    def test_redact_helpers(self):
        home = os.path.expanduser("~")
        self.assertEqual(server._redact_text("x" + home + "/y"), "x~/y")
        self.assertEqual(server._redact_obj({"a": [home + "/b"], "c": 3}), {"a": ["~/b"], "c": 3})

    def test_home_paths_redacted_in_responses_and_on_disk(self):
        home = os.path.expanduser("~")
        state = make_state(items=[{
            "name": "Meal prep jar", "role": "staple", "spend": 3.0,
            "notes": "recipe kept at " + home + "/recipes/jar.md",
        }])
        with Service():
            code, body = post({"method": "groceryflywheel.analyze", "params": {"state_json": json.dumps(state)}})
            self.assertEqual(code, 200)
            serialized = json.dumps(body)
            self.assertNotIn(home, serialized)
            self.assertIn("~/recipes/jar.md", serialized)

            code, dash = post({"method": "groceryflywheel.dashboard", "params": {
                "state_json": json.dumps(state), "filename": "redaction-check.html"}})
            self.assertEqual(code, 200)
            with open(os.path.join(ADDON_ROOT, dash["output_path"])) as f:
                on_disk = f.read()
            self.assertNotIn(home, on_disk)  # redaction happens BEFORE the write
            self.assertIn("~/recipes/jar.md", on_disk)

    def test_no_home_paths_in_committed_tree(self):
        needle = (os.sep + "Users" + os.sep).encode()
        for root, dirs, files in os.walk(ADDON_ROOT):
            dirs[:] = [d for d in dirs if d not in ("var", "__pycache__", ".git")]
            for name in files:
                if name.endswith((".pyc", ".DS_Store")):
                    continue
                path = os.path.join(root, name)
                with open(path, "rb") as f:
                    self.assertNotIn(needle, f.read(), f"home path leaked in {path}")


if __name__ == "__main__":
    unittest.main()
