"""The panel registry: an ordered list of (name, span, render) callables.

Deliberately NOT a framework — no classes to subclass, no plugins, no
registration decorators. A panel is a function from analysis to HTML;
adding one means appending an entry here and nowhere else. The order
below is the D1 decision (2026-08-14): first-wow cards → core runway →
dietary + easy food → freshness + trips → evidence, corrections, cart
plan → tables.
"""

from __future__ import annotations

import json
from html import escape
from typing import Any, Callable

from .layout import header_line, page_shell

PanelRender = Callable[[dict[str, Any]], str]


def _panel(name: str, span: str, render: PanelRender) -> dict[str, Any]:
    return {"name": name, "span": span, "render": render}


# --- individual panels -------------------------------------------------

def _first_wow(a: dict[str, Any]) -> str:
    wow = a.get("first_wow") or {}
    savings = float(wow.get("estimated_unit_savings", 0) or 0)
    return f"""
      <article class="panel span-12 wow">
        <h2>First Look</h2>
        <div class="card-row">
          <div><h2>Potential Unit Savings</h2><div class="metric">${savings:.2f}</div></div>
          <div><h2>Best Sourcing Move</h2><div class="metric" style="font-size:1.1rem">{escape(str(wow.get('best_sourcing_move', '—')))}</div></div>
          <div><h2>Runway</h2><div class="metric" style="font-size:1.1rem">{escape(_runway_text(a))}</div></div>
        </div>
        <p class="muted">{escape(str(wow.get('headline', '')))}</p>
      </article>"""


def _metrics(a: dict[str, Any]) -> str:
    order = a["order"]
    consumed_pct = a["known_consumed_fraction"] * 100
    return f"""
      <article class="panel span-12">
        <div class="card-row">
          <div><h2>Known Depletion</h2><div class="metric">${a['consumed_value']:.2f}</div>
            <p class="muted">{consumed_pct:.1f}% of order value observed consumed.</p></div>
          <div><h2>Runway</h2><div class="metric" style="font-size:1.3rem">{escape(_runway_text(a))}</div>
            <p class="muted">Estimate is based on observed depletion, not a full pantry audit.</p></div>
          <div><h2>Order Total</h2><div class="metric">${float(order['total']):.2f}</div>
            <p class="muted">{a['days_elapsed']} elapsed day(s).</p></div>
        </div>
      </article>"""


def _runway_text(a: dict[str, Any]) -> str:
    remaining = a.get("estimated_days_remaining")
    return f"{remaining} days remaining" if remaining is not None else "Not enough depletion data"


def _role_summary(a: dict[str, Any]) -> str:
    body = "\n".join(
        f"<tr><td>{escape(r['role'])}</td><td>${r['spend']:.2f}</td>"
        f"<td>${r['consumed']:.2f}</td><td>{_bar(r['consumed_fraction'])}</td></tr>"
        for r in a.get("role_summary", [])
    )
    return ("<article class='panel span-6'><h2>Role Summary</h2>"
            "<table><thead><tr><th>Role</th><th>Spend</th><th>Consumed</th><th>Drawdown</th></tr></thead>"
            f"<tbody>{body}</tbody></table></article>")


def _preferences(a: dict[str, Any]) -> str:
    rows = a.get("preferences", [])
    if not rows:
        return "<article class='panel span-6'><h2>Preference Signals</h2><p class='muted'>No preference signals yet.</p></article>"
    body = "".join(
        f"<p><strong>{escape(r['key'])}</strong><br>{escape(r.get('signal', ''))}<br>"
        f"<span class='muted'>{escape(r.get('rule', ''))}</span></p>"
        for r in rows
    )
    return f"<article class='panel span-6'><h2>Preference Signals</h2>{body}</article>"


def _dietary(a: dict[str, Any]) -> str:
    evaluations = a.get("dietary_evaluations", [])
    profiles = a.get("dietary_profiles", [])
    if not profiles:
        return ("<article class='panel span-6'><h2>Dietary Restrictions</h2>"
                "<p class='muted'>No dietary restriction profile configured.</p></article>")
    counts: dict[str, int] = {}
    for e in evaluations:
        counts[e["result"]] = counts.get(e["result"], 0) + 1
    chips = "".join(
        f"<span class='tag {cls}'>{escape(k)}: {v}</span>"
        for k, v in sorted(counts.items())
        for cls in [{"blocked": "critical", "needs_review": "review"}.get(k, "ok")]
    )
    profile_chips = "".join(
        f"<span class='tag'>{escape(p.get('label', 'Dietary profile'))}</span>"
        for p in profiles
    )
    flagged_items = sorted({e["item"] for e in evaluations if e["result"] in ("blocked", "needs_review")})
    flagged = (
        "<p class='muted'>Flagged for review: " + escape(", ".join(flagged_items)) + "</p>"
        if flagged_items else ""
    )
    return (f"<article class='panel span-6'><h2>Dietary Restrictions</h2>"
            f"<p>{profile_chips}</p><p>{chips}</p>{flagged}</article>")


def _easy_food(a: dict[str, Any]) -> str:
    summary = a.get("easy_food") or {}
    if not summary or summary.get("count", 0) == 0:
        return ("<article class='panel span-6'><h2>Easy Food</h2>"
                "<p class='muted'>No unopened top-ups in the easy-food window.</p></article>")
    items = "".join(
        f"<li><strong>{escape(str(r['name']))}</strong> "
        f"({escape(str(r['role']))}, {escape(str(r['age_label']))}) — "
        f"rotate into a meal before the next top-up duplicates it.</li>"
        for r in summary["items"]
    )
    return (f"<article class='panel span-6'><h2>Easy Food</h2>"
            f"<p><strong>{summary['count']}</strong> unopened top-up(s):</p><ul>{items}</ul></article>")


def _freshness(a: dict[str, Any]) -> str:
    summary = a.get("freshness")
    if not summary:
        return "<article class='panel span-12'><h2>Data Freshness</h2><p class='muted'>No freshness data.</p></article>"
    parts = [f"<p>{summary.get('fresh_count', 0)} priced recently, "
             f"{summary.get('stale_count', 0)} unpriced or stale.</p>"]
    flagged = [f"{escape(r['name'])} ({escape(r['age_label'])}, {escape(r['reason'])})"
               for r in summary.get("items", []) if r["pricing_stale"]]
    if flagged:
        parts.append("<p><strong>Flagged items:</strong> " + ", ".join(flagged) + "</p>")
    stale_sourcing = [f"{escape(r['item'])} ({escape(r['age_label'])})"
                      for r in summary.get("stale_sourcing", [])]
    if stale_sourcing:
        parts.append("<p><strong>Stale sourcing research:</strong> " + ", ".join(stale_sourcing) + "</p>")
    return "<article class='panel span-12'><h2>Data Freshness</h2>" + "".join(parts) + "</article>"


def _trips(a: dict[str, Any]) -> str:
    summary = a.get("visits_summary") or {}
    if not summary or summary.get("visit_count", 0) == 0:
        return ("<article class='panel span-6'><h2>Trip Overhead</h2>"
                "<p class='muted'>No visits recorded yet. Use <code>capture-visit</code> to log a trip.</p></article>")
    by_type = summary.get("by_type", {}) or {}
    by_type_min = summary.get("by_type_minutes", {}) or {}
    lines = [f"<p><strong>{summary['visit_count']}</strong> visit(s), "
             f"<strong>{summary.get('total_minutes', 0)}</strong> minutes total.</p>"]
    if by_type:
        items = ", ".join(f"{escape(t)}: {by_type[t]} ({by_type_min.get(t, 0)} min)"
                          for t in sorted(by_type))
        lines.append(f"<p class='muted'>By type — {items}.</p>")
    amortized = summary.get("amortized_cost_total", 0.0)
    lines.append(
        f"<p>Amortized time cost: <strong>${amortized:.2f}</strong></p>" if amortized
        else "<p class='muted'>Set an hourly value in the state to see amortized cost.</p>"
    )
    return "<article class='panel span-6'><h2>Trip Overhead</h2>" + "".join(lines) + "</article>"


def _cart_plan(a: dict[str, Any]) -> str:
    plan = a.get("cart_plan") or {}
    items = plan.get("items", [])
    note = ("<p class='approve-note'>Everything needs your approval. "
            "No checkout surface exists.</p>")
    if not items:
        return (f"<article class='panel span-6'><h2>Internal Cart Plan</h2>{note}"
                "<p class='muted'>No cart plan yet — add sourcing research or deplete items.</p></article>")
    body = "\n".join(
        f"<tr><td>{escape(str(i.get('item', '')))}</td><td>{escape(str(i.get('action', '')))}</td>"
        f"<td>{escape(str(i.get('source', '')))}</td><td>{escape(str(i.get('approval_state', '')))}</td></tr>"
        for i in items
    )
    return (f"<article class='panel span-6'><h2>Internal Cart Plan</h2>{note}"
            f"<table><thead><tr><th>Item</th><th>Action</th><th>Source</th><th>Approval</th></tr></thead>"
            f"<tbody>{body}</tbody></table></article>")


def _items(a: dict[str, Any]) -> str:
    body = "\n".join(
        f"<tr><td>{escape(r['name'])}</td><td>{escape(r['role'])}</td>"
        f"<td>{escape(r.get('category', ''))}</td>"
        f"<td>${r['spend']:.2f}</td><td>{r['consumed_fraction'] * 100:.0f}%</td>"
        f"<td>{escape(r.get('notes', ''))}</td><td>{_evidence_drawer(r)}</td></tr>"
        for r in a.get("items", [])
    )
    return ("<article class='panel span-12'><h2>Items</h2>"
            "<table><thead><tr><th>Item</th><th>Role</th><th>Category</th><th>Spend</th>"
            "<th>Consumed</th><th>Notes</th><th>Evidence</th></tr></thead>"
            f"<tbody>{body}</tbody></table></article>")


def _evidence_drawer(item: dict[str, Any]) -> str:
    rows = item.get("product_evidence") or []
    if not rows:
        return "<span class='muted'>none</span>"
    parts = []
    for row in rows:
        label = f"{row.get('evidence_type', 'evidence')} · {row.get('source', '')} · {row.get('checked_date', '')}"
        content = ", ".join(
            str(part) for field in ("ingredients", "allergen_statements", "certifications")
            for part in (row.get(field) or [])[:4]
        )
        parts.append(f"<details><summary>{escape(label)}</summary>"
                     f"<p class='muted'>{escape(content)}</p></details>")
    return "".join(parts)


def _substitutions(a: dict[str, Any]) -> str:
    rows = a.get("substitutions", [])
    if not rows:
        return ("<article class='panel span-6'><h2>Substitutions</h2>"
                "<p class='muted'>No substitution candidates yet.</p></article>")
    body = "\n".join(
        f"<tr><td>{escape(r['candidate'])}</td><td>{escape(r['current'])}</td>"
        f"<td>${float(r.get('candidate_unit_price', 0)):.3f}</td><td>{escape(r.get('fit', ''))}</td>"
        f"<td>{_dietary_badge(r.get('dietary_status'))}</td><td>{escape(r.get('read', ''))}</td></tr>"
        for r in rows
    )
    return ("<article class='panel span-6'><h2>Substitutions</h2>"
            "<table><thead><tr><th>Candidate</th><th>Replaces</th><th>Unit</th><th>Fit</th>"
            "<th>Dietary</th><th>Read</th></tr></thead>"
            f"<tbody>{body}</tbody></table></article>")


def _dietary_badge(status: Any) -> str:
    value = str(status or "")
    if value in ("blocked",):
        return f"<span class='tag critical'>{escape(value)}</span>"
    if value in ("needs_review", "warn"):
        return f"<span class='tag review'>{escape(value)}</span>"
    if value:
        return f"<span class='tag ok'>{escape(value)}</span>"
    return ""


def _sourcing(a: dict[str, Any]) -> str:
    rows = a.get("sourcing_research", [])
    if not rows:
        return ("<article class='panel span-6'><h2>Sourcing Research</h2>"
                "<p class='muted'>No sourcing research yet.</p></article>")
    body = []
    for row in rows:
        alternatives = row.get("alternatives", [])
        best = alternatives[0] if alternatives else {}
        body.append(
            f"<tr><td>{escape(row['item'])}</td><td>{escape(row.get('current_source', ''))}</td>"
            f"<td>{escape(best.get('source', ''))}</td><td>${float(best.get('unit_price', 0)):.3f}</td>"
            f"<td>{escape(best.get('savings', ''))}</td><td>{escape(row.get('recommendation', ''))}</td></tr>"
        )
    return ("<article class='panel span-6'><h2>Sourcing Research</h2>"
            "<table><thead><tr><th>Item</th><th>Current</th><th>Best alternative</th><th>Unit</th>"
            "<th>Savings</th><th>Read</th></tr></thead><tbody>" + "".join(body) + "</tbody></table></article>")


def _script_json(value: Any) -> str:
    """JSON that is safe to embed inside a <script> block.

    json.dumps alone leaves ``</script>``, ``&``, and the Unicode line
    separators intact, so data could close the script context and execute
    attacker JS (the XSS the adversarial QA pass found). Escaping them as
    JSON unicode escapes keeps the payload valid JS-in-JSON while making
    breakout impossible.
    """
    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(chr(0x2028), "\\u2028")
        .replace(chr(0x2029), "\\u2029")
    )


def _corrections_capture(a: dict[str, Any]) -> str:
    consent = a.get("consent") or {}
    if consent.get("correction_telemetry") not in ("local_only", "hosted_opt_in"):
        return ""
    item_names = [r["name"] for r in a.get("items", [])]
    options = "".join(f"<option>{escape(n)}</option>" for n in item_names)
    buttons = "".join(
        f"<button class='correction' data-signal='{escape(s)}' onclick=\"capture('{escape(s)}')\">{escape(s.replace('_', ' '))}</button>"
        for s in ("never_again", "buy_elsewhere", "wrong_format", "too_expensive",
                  "good_default", "emergency_only")
    )
    payload = _script_json({"items": item_names})
    return f"""
      <article class="panel span-12" id="corrections">
        <h2>Correction Capture</h2>
        <p class="muted">Record durable signals — kept local, appended to a JSONL file you download. Nothing is sent anywhere.</p>
        <p><select id="correction-item">{options}</select></p>
        <p>{buttons}</p>
        <p><a id="correction-download" download="corrections.jsonl"><button class="correction">Download JSONL</button></a>
        <span class="muted" id="correction-count"></span></p>
        <script>
          var log = [];
          function capture(signal) {{
            var item = document.getElementById("correction-item").value;
            log.push({{"item": item, "signal": signal, "created_at": new Date().toISOString().slice(0, 10)}});
            document.getElementById("correction-count").textContent = log.length + " captured";
          }}
          document.getElementById("correction-download").addEventListener("click", function () {{
            var blob = new Blob([log.map(function (e) {{ return JSON.stringify(e); }}).join("\\n")], {{type: "application/jsonl"}});
            this.href = URL.createObjectURL(blob);
          }});
          var _state = {payload};
        </script>
      </article>"""


def _pulses(a: dict[str, Any]) -> str:
    rows = a.get("pulses", [])
    if not rows:
        return "<article class='panel span-12'><h2>Recent Pulses</h2><p class='muted'>No pulses yet.</p></article>"
    body = "".join(
        # tolerant field access: some hand-edited states use 'note' (compat fix, 2026-08-14)
        f"<p><span class='tag'>{escape(r['date'])}</span>{escape(r.get('text', r.get('note', '')))}</p>"
        for r in rows[-5:]
    )
    return f"<article class='panel span-12'><h2>Recent Pulses</h2>{body}</article>"


def _bar(fraction: float) -> str:
    pct = max(0, min(100, round(float(fraction) * 100)))
    return f"<div class='bar' aria-label='{pct}% consumed'><span style='width:{pct}%'></span></div>"


# --- the registry --------------------------------------------------------

PANELS: list[dict[str, Any]] = [
    _panel("first_wow", "span-12", _first_wow),
    _panel("metrics", "span-12", _metrics),
    _panel("role_summary", "span-6", _role_summary),
    _panel("preferences", "span-6", _preferences),
    _panel("dietary", "span-6", _dietary),
    _panel("easy_food", "span-6", _easy_food),
    _panel("freshness", "span-12", _freshness),
    _panel("trips", "span-6", _trips),
    _panel("cart_plan", "span-6", _cart_plan),
    _panel("items", "span-12", _items),
    _panel("substitutions", "span-6", _substitutions),
    _panel("sourcing", "span-6", _sourcing),
    _panel("corrections_capture", "span-12", _corrections_capture),
    _panel("pulses", "span-12", _pulses),
]


def render_dashboard(analysis: dict[str, Any]) -> str:
    """Render the analysis through the panel registry into the dark shell."""
    panels_html = "\n".join(
        f"      {panel['render'](analysis)}"
        for panel in PANELS
    )
    return page_shell(header_line(analysis), panels_html)
