"""Page shell and theme for the dashboard — the dark command-center
aesthetic chosen in decision D1 (2026-08-14). Panels render into the
grid; this module owns everything a panel should NOT define."""

from __future__ import annotations

from html import escape

CSS = """
    :root {
      color-scheme: dark;
      --bg: #0e1210;
      --panel: #161d19;
      --panel-edge: #243029;
      --ink: #e6ece7;
      --muted: #8fa398;
      --green: #4ade80;
      --green-dim: #2f7d5c;
      --blue: #7ab8e8;
      --gold: #e8b04b;
      --red: #f87171;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background:
        radial-gradient(1200px 500px at 20% -10%, #16211b 0%, transparent 60%),
        var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }
    main { max-width: 1180px; margin: 0 auto; padding: 28px; }
    header { display: grid; gap: 10px; margin-bottom: 22px; }
    h1, h2 { margin: 0; }
    h1 { font-size: clamp(1.8rem, 5vw, 3.4rem); line-height: .95; letter-spacing: .01em; }
    h2 { font-size: .78rem; text-transform: uppercase; letter-spacing: .12em; color: var(--muted); }
    .grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--panel-edge);
      border-radius: 10px;
      padding: 16px;
      box-shadow: 0 1px 0 rgba(0,0,0,.35);
    }
    .span-4 { grid-column: span 4; }
    .span-6 { grid-column: span 6; }
    .span-12 { grid-column: span 12; }
    .metric { font-size: 1.9rem; font-weight: 750; margin-top: 6px; }
    .muted { color: var(--muted); }
    table { width: 100%; border-collapse: collapse; font-size: .9rem; }
    th, td { border-bottom: 1px solid var(--panel-edge); padding: 9px 8px; text-align: left; vertical-align: top; }
    th { color: var(--muted); font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; }
    .bar { height: 10px; background: #0b0f0d; border-radius: 999px; overflow: hidden; min-width: 80px; }
    .bar > span { display: block; height: 100%; background: var(--green-dim); }
    .tag {
      display: inline-block; border: 1px solid var(--panel-edge); border-radius: 999px;
      padding: 3px 9px; margin: 3px 4px 3px 0; font-size: .8rem;
    }
    .tag.critical { border-color: var(--red); color: var(--red); }
    .tag.review { border-color: var(--gold); color: var(--gold); }
    .tag.ok { border-color: var(--green); color: var(--green); }
    .card-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
    .wow { border-left: 3px solid var(--green); }
    .approve-note { color: var(--gold); }
    button.correction {
      background: #1d251f; border: 1px solid var(--panel-edge); color: var(--ink);
      border-radius: 6px; padding: 4px 8px; font-size: .78rem; cursor: pointer;
    }
    button.correction:hover { border-color: var(--green); }
    details { margin: 4px 0; }
    summary { cursor: pointer; color: var(--muted); font-size: .85rem; }
    @media (max-width: 760px) {
      main { padding: 16px; }
      .span-4, .span-6, .card-row { grid-column: span 12; }
      .card-row { grid-template-columns: 1fr; }
      table { font-size: .82rem; }
    }
"""


def page_shell(header_html: str, panels_html: str) -> str:
    """Assemble the full self-contained HTML document."""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Grocery Flywheel Dashboard</title>
  <style>{CSS}</style>
</head>
<body>
  <main>
    <header>
      <p class="muted">Local-first household replenishment — command center</p>
      <h1>Grocery Flywheel</h1>
      {header_html}
    </header>
    <section class="grid">
{panels_html}
    </section>
  </main>
</body>
</html>
"""


def header_line(analysis: dict) -> str:
    order = analysis["order"]
    surface = analysis.get("inventory_surface") or {}
    surface_label = surface.get("label") or surface.get("type") or "Inventory surface"
    channel = analysis.get("acquisition_channel", "unknown")
    objective = analysis.get("objective_label")
    objective_note = f" Objective: {escape(str(objective))}." if objective else ""
    warnings = analysis.get("data_warnings") or []
    warning_html = (
        "<p style='color: var(--gold)'>⚠ " + escape(" ".join(warnings)) + "</p>"
        if warnings else ""
    )
    return (
        f"<p>{escape(str(surface_label))} via {escape(str(channel))}. "
        f"{escape(order['store'])} run from {escape(order['date'])}, "
        f"analyzed as of {escape(analysis['as_of'])}.{objective_note}</p>"
        f"{warning_html}"
    )
