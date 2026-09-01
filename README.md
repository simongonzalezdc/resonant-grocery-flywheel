# Grocery Flywheel — ResonantOS add-on

**Local-first, human-approves-everything groceries.** Those two values are the
whole reason this tool belongs in this community: your food and habit data
never leaves your machine, and the flywheel never spends a dollar you did not
personally approve. It tracks what you bought, notices what you've used,
flags what's going stale, and drafts the next cart — **you** say yes.

The engine is [grocery-flywheel](https://github.com/simongonzalezdc/grocery-flywheel)
(MIT, vendored files sha256-pinned (VENDOR-PINS.json)), vendored byte-identical under `vendor/` and
wrapped by a thin local service. The wrapper adds no dependencies: Python 3.10+
standard library only. No accounts, no cloud, no telemetry.

## Honest surface

This add-on wraps exactly the verbs the upstream MCP server exposes to AI
assistants — the tool's real headless surface — plus its status:

| Verb | Upstream tool | What it actually does |
| --- | --- | --- |
| `groceryflywheel.status` | — | version, busy flag, last dashboard |
| `groceryflywheel.analyze` | `analyze_replenishment_state` | runway, depletion, roles, freshness, dietary evaluations, substitutions |
| `groceryflywheel.dietary` | `evaluate_dietary` | fail-closed safety: restrictions without current label evidence come back `needs_review`, never `safe` |
| `groceryflywheel.sourcing` | `summarize_sourcing_research` | open sourcing questions + decision boundaries recorded in the state |
| `groceryflywheel.plan` | `plan_next_cart` | next-cart draft; every item is `needs_human_approval`, and the vendored engine itself raises unless `checkout_available` is `false` |
| `groceryflywheel.dashboard` | `render_replenishment_dashboard` | the dark command-center HTML, written only under `var/dashboards/` |

**What is deliberately NOT wrapped, declared plainly:**

- **Checkout.** It does not exist anywhere in the upstream engine by design
  (`checkout_available` is structurally `false`; upstream ships a test that
  fails if that ever changes). Nothing was removed — there is nothing to remove.
- **`state_path` / `output_path`.** The upstream MCP tools accept filesystem
  paths; this wrapper does not. State arrives inline as `state_json` (at most
  60000 characters — it must fit the 64KB request body), and dashboard HTML is
  written only inside this addon's `var/dashboards/`. No filesystem capability
  is requested; the manifest requests **zero capabilities**.
- **Corrections, capture-visit, and retailer-import CLI flows.** Those are
  upstream CLI workflows (subprocess entry points), not part of the MCP
  surface; this service spawns no subprocesses, so they are out of scope here.
- **Upstream quirk, preserved and declared:** upstream's
  `analyze_replenishment_state` schema advertises `objective` but its handler
  does not apply it (only `evaluate_dietary` and `plan_next_cart` do). This
  wrapper mirrors upstream exactly; to get an objective-aware analysis, put
  `objective` in the state document itself.

## Privacy posture

Food and habit data is personal. Following the Innerscape posture: the data
surface is data-bearing, and **nothing leaves the machine** — the service
binds loopback only, calls the vendored engine in-process, writes only under
`var/`, requests zero capabilities, and keeps no telemetry. Every response and
every persisted file passes through home-path redaction before it exists. The
only state used by the test suite is the upstream sanitized example and
synthetic fixtures built in the tests.

## Running it

    python3 server.py          # listens on http://127.0.0.1:4899 (the manifest entrypoint)

    curl -s http://127.0.0.1:4899/health
    curl -s -X POST http://127.0.0.1:4899/ -H 'Content-Type: application/json' \
      -d '{"method":"groceryflywheel.plan","params":{"state_json":"...","mode":"pickup"}}'
    curl -s -X POST http://127.0.0.1:4899/ -H 'Content-Type: application/json' \
      -d '{"method":"groceryflywheel.dashboard","params":{"state_json":"...","filename":"week.html"}}'

A ready-made state to try lives at `vendor/examples/sample_state.json`
(upstream's sanitized example). Environment: `GROCERYFLYWHEEL_PORT` (dev only —
the manifest declares 4899). The service binds `127.0.0.1` only, spawns no
subprocesses, and exits with code 78 if the port cannot be bound.

## Tests

    python3 -m unittest discover -s tests        # wrapper suite
    sh run-validator-check.sh <path-to-2.0.0-alpha-clone>  # manifest vs the real validator
    cd vendor && PYTHONPATH=. python3 -m pytest tests/ -q   # upstream suite, unmodified (188 tests)

`vendor/` is hash-pinned against vendored files sha256-pinned (VENDOR-PINS.json): the wrapper suite
fails loudly if any vendored engine file, vendored upstream test, or vendored
example drifts by a single byte. The vendored upstream suite is upstream's own
tests unmodified, minus `test_quickstart.py` (it shells out to installed
`grocery-flywheel` console scripts and a `docs/` tree — environmental, not
engine, coverage; the wrapper does not expose the CLI).

## License

MIT — see LICENSE. The vendored grocery-flywheel engine is MIT,
Pastorsimon1798 (see upstream repository).
