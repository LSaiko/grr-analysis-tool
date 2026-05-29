"""
msa_toolkit.dashboard
=====================
Shared Chart.js HTML generation helpers.  Every function returns a
plain string of HTML/JS.  Combine fragments using ``page_template()``
to produce a self-contained single-file dashboard.

Design rules:
- No runtime dependencies beyond the stdlib and Chart.js 4.5.1 (CDN).
- Each function is independently testable — returns a str, no side
  effects.
- Every generated page embeds a version string and the standard
  21 CFR 820.72 regulatory footer.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = [
    "page_template",
    "gauge_meter",
    "bar_chart",
    "line_chart",
    "metrics_grid",
    "operator_toggles",
    "metrics_table_html",
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_CHARTJS_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js"

_BASE_CSS = """
:root {
  --navy:#1A3A5C; --teal:#16A085; --orange:#E67E22;
  --green:#27AE60; --red:#C0392B; --grey:#95A5A6;
  --bg:#f0f3f7; --card:#fff; --border:#d0d7e2;
  --text:#1a2332; --muted:#667388;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
     background:var(--bg);color:var(--text);font-size:14px}
header{background:var(--navy);color:#fff;padding:16px 28px;
       display:flex;justify-content:space-between;align-items:center;
       flex-wrap:wrap;gap:8px}
header h1{font-size:1.2rem;font-weight:700}
header .meta{font-size:.78rem;opacity:.75;text-align:right;line-height:1.6}
main{max-width:1200px;margin:22px auto;padding:0 18px}
.grid{display:grid;gap:18px}
.grid-2{grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;
      padding:18px 20px;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.card h2{font-size:.85rem;font-weight:700;color:var(--navy);
         text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px}
.chart-wrap{position:relative;height:260px}
.chart-wrap-lg{position:relative;height:320px}
.kpi-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.kpi{background:#f7f9fc;border:1px solid var(--border);border-radius:6px;padding:10px 12px}
.kpi-label{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.kpi-value{font-size:1.3rem;font-weight:700;color:var(--navy);margin-top:2px}
.kpi-sub{font-size:.7rem;color:var(--muted);margin-top:1px}
table{width:100%;border-collapse:collapse;font-size:.82rem}
th{background:var(--navy);color:#fff;padding:7px 10px;
   text-align:left;font-weight:600;font-size:.75rem}
td{padding:6px 10px;border-bottom:1px solid var(--border)}
tr:nth-child(even) td{background:#f7f9fc}
tr.hl td{font-weight:700}
.tag{display:inline-block;padding:1px 8px;border-radius:3px;
     font-size:.72rem;font-weight:700}
.tag-ok {background:#d5f5e3;color:#1a5c2e}
.tag-mg {background:#fdebd0;color:#7a3a00}
.tag-bad{background:#fadbd8;color:#5c1a1a}
.tag-info{background:#e8f0fa;color:#1a3a5c}
.toggle-row{display:flex;gap:8px;flex-wrap:wrap}
.op-btn{padding:4px 14px;border-radius:4px;border:2px solid;
        font-size:.78rem;font-weight:600;cursor:pointer;
        transition:opacity .15s;background:#fff}
.op-btn.off{opacity:.35}
footer{text-align:center;font-size:.7rem;color:var(--muted);
       padding:20px;border-top:1px solid var(--border);margin-top:28px}
"""

_REG_FOOTER = (
    "msa_toolkit &mdash; AIAG MSA 4th Edition &bull; "
    "Regulatory basis: 21 CFR 820.72 (FDA QSR)"
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def page_template(
    title: str,
    body_html: str,
    metadata: Optional[Dict[str, str]] = None,
    version: str = "0.1.0",
    extra_scripts: str = "",
) -> str:
    """
    Wrap body HTML in a full self-contained HTML page.

    Args:
        title:        Page ``<title>`` and ``<h1>`` text.
        body_html:    Inner HTML to place inside ``<main>``.
        metadata:     Key/value pairs shown in the header right column
                      (e.g. ``{"Equipment": "CMM SN-001"}``).
        version:      msa_toolkit version string embedded in footer.
        extra_scripts: Raw ``<script>`` blocks appended before ``</body>``.

    Returns:
        Complete HTML string ready to write to a ``.html`` file.

    Example:
        >>> html = page_template("My Report", "<p>Hello</p>",
        ...                      metadata={"Date": "2026-01-01"})
    """
    meta_html = ""
    if metadata:
        meta_html = "<br>".join(
            f"<b>{k}:</b> {v}" for k, v in metadata.items()
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title>
<script src="{_CHARTJS_CDN}"></script>
<style>{_BASE_CSS}</style>
</head>
<body>
<header>
  <div>
    <h1>&#x1F4CA; {title}</h1>
    <div style="font-size:.75rem;opacity:.7;margin-top:2px">
      AIAG MSA 4th Edition &mdash; msa_toolkit v{version}
    </div>
  </div>
  <div class="meta">{meta_html}</div>
</header>
<main>
{body_html}
</main>
<footer>
  {_REG_FOOTER} &bull; v{version}
</footer>
{extra_scripts}
</body>
</html>"""


def gauge_meter(
    value: float,
    label: str = "%GRR",
    accept_threshold: float = 10.0,
    marginal_threshold: float = 30.0,
    max_value: float = 100.0,
) -> str:
    """
    Return HTML for a colored gauge meter strip with a pin marker.

    The track is divided into three zones proportional to the thresholds:
    green (0–accept), amber (accept–marginal), red (marginal–max).

    Args:
        value:              The metric value to mark on the gauge.
        label:              Short label shown above the pin.
        accept_threshold:   Upper boundary of the green zone.
        marginal_threshold: Upper boundary of the amber zone.
        max_value:          Right edge of the gauge scale.

    Returns:
        HTML string (a ``<div class="card">`` block).

    Example:
        >>> html = gauge_meter(17.0, label="%GRR")
    """
    pct_accept  = 100.0 * accept_threshold  / max_value
    pct_marginal = 100.0 * (marginal_threshold - accept_threshold) / max_value
    pct_bad     = 100.0 * (max_value - marginal_threshold) / max_value
    pin_pct     = min(100.0 * value / max_value, 100.0)

    verdict = (
        "Acceptable"   if value <= accept_threshold
        else "Marginal"   if value <= marginal_threshold
        else "Unacceptable"
    )
    pin_color = (
        "var(--green)"  if value <= accept_threshold
        else "var(--orange)" if value <= marginal_threshold
        else "var(--red)"
    )

    return f"""
<div class="card">
  <h2>{label} Gauge</h2>
  <div style="display:flex;flex-direction:column;align-items:center;gap:10px;padding:8px 0">
    <div style="width:100%;height:18px;border-radius:9px;overflow:hidden;display:flex">
      <div style="flex:{pct_accept:.1f};background:var(--green)"></div>
      <div style="flex:{pct_marginal:.1f};background:var(--orange)"></div>
      <div style="flex:{pct_bad:.1f};background:var(--red)"></div>
    </div>
    <div style="width:100%;position:relative;height:24px">
      <div style="position:absolute;left:{pin_pct:.2f}%;transform:translateX(-50%);
                  display:flex;flex-direction:column;align-items:center;
                  font-size:.8rem;font-weight:700;color:{pin_color}">
        <div style="width:2px;height:12px;background:{pin_color};margin-bottom:2px"></div>
        {value:.1f}%
      </div>
    </div>
    <div style="width:100%;display:flex;justify-content:space-between;
                font-size:.7rem;color:var(--muted)">
      <span>0%</span>
      <span>{accept_threshold:.0f}%</span>
      <span>{marginal_threshold:.0f}%</span>
      <span>{max_value:.0f}%</span>
    </div>
  </div>
  <div style="margin-top:8px;text-align:center">
    <span class="tag {'tag-ok' if verdict=='Acceptable' else 'tag-mg' if verdict=='Marginal' else 'tag-bad'}">
      {verdict.upper()}
    </span>
    &nbsp;{label} = <b>{value:.2f}%</b>
  </div>
</div>"""


def bar_chart(
    labels: Sequence[str],
    values: Sequence[float],
    title: str,
    bar_colors: Optional[Sequence[str]] = None,
    y_label: str = "",
    thresholds: Optional[Sequence[Tuple[float, str, str]]] = None,
    canvas_id: str = "bar-chart",
    height_px: int = 260,
) -> str:
    """
    Return HTML+JS for a Chart.js bar chart with optional threshold lines.

    Args:
        labels:      Bar category labels.
        values:      Numeric values corresponding to each label.
        title:       Chart title shown above the canvas.
        bar_colors:  Per-bar hex colors.  Defaults to NAVY for all bars.
        y_label:     Y-axis label string.
        thresholds:  List of ``(value, hex_color, label)`` dashed threshold
                     lines drawn via a custom plugin.
        canvas_id:   HTML ``id`` attribute for the canvas element.
        height_px:   Pixel height of the chart wrapper div.

    Returns:
        HTML string containing a ``<div class="card">`` with an embedded
        canvas and inline ``<script>`` block.

    Example:
        >>> html = bar_chart(
        ...     ["EV", "AV", "GRR", "PV"],
        ...     [10.1, 13.7, 17.0, 98.5],
        ...     title="Variance Components",
        ...     thresholds=[(10, "#27AE60", "10%"), (30, "#C0392B", "30%")],
        ... )
    """
    if bar_colors is None:
        bar_colors = ["#1A3A5C"] * len(labels)

    threshold_plugin = ""
    plugin_reg = ""
    if thresholds:
        lines_js = json.dumps(
            [[t[0], t[1], t[2]] for t in thresholds]
        )
        threshold_plugin = f"""
const _thresh_{canvas_id} = {{
  id: 'thresh_{canvas_id}',
  afterDraw(chart) {{
    const {{ctx, chartArea: {{left, right}}, scales: {{y}}}} = chart;
    {lines_js}.forEach(([v, c, lbl]) => {{
      const yp = y.getPixelForValue(v);
      ctx.save();
      ctx.setLineDash([5,4]); ctx.strokeStyle=c; ctx.lineWidth=1.5;
      ctx.beginPath(); ctx.moveTo(left,yp); ctx.lineTo(right,yp); ctx.stroke();
      ctx.setLineDash([]); ctx.fillStyle=c; ctx.font='600 10px sans-serif';
      ctx.textAlign='right'; ctx.fillText(lbl, right-4, yp-4);
      ctx.restore();
    }});
  }}
}};"""
        plugin_reg = f"Chart.register(_thresh_{canvas_id});"

    max_y = max(list(values) + [t[0] for t in (thresholds or [])])
    suggested_max = (int(max_y / 10) + 2) * 10

    return f"""
<div class="card">
  <h2>{title}</h2>
  <div class="chart-wrap" style="height:{height_px}px">
    <canvas id="{canvas_id}"></canvas>
  </div>
</div>
<script>
(function() {{
  {threshold_plugin}
  {plugin_reg}
  new Chart(document.getElementById('{canvas_id}'), {{
    type: 'bar',
    data: {{
      labels: {json.dumps(list(labels))},
      datasets: [{{
        data: {json.dumps([float(v) for v in values])},
        backgroundColor: {json.dumps(list(bar_colors))},
        borderRadius: 4,
      }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{
        legend: {{display: false}},
        tooltip: {{callbacks: {{label: c => ' ' + c.parsed.y.toFixed(2)}}}}
      }},
      scales: {{
        y: {{
          suggestedMax: {suggested_max},
          title: {{display: {'true' if y_label else 'false'}, text: {json.dumps(y_label)}}},
          ticks: {{font: {{size: 10}}}},
          grid: {{color: '#e8ecf0'}}
        }},
        x: {{grid: {{display: false}}, ticks: {{font: {{size: 10}}}}}}
      }}
    }}
  }});
}})();
</script>"""


def line_chart(
    series: Dict[str, Sequence[float]],
    x_labels: Sequence[str],
    title: str,
    ucl: Optional[float] = None,
    lcl: Optional[float] = None,
    cl:  Optional[float] = None,
    y_label: str = "",
    canvas_id: str = "line-chart",
    height_px: int = 260,
    op_colors: Optional[Sequence[str]] = None,
) -> str:
    """
    Return HTML+JS for a Chart.js line chart with optional UCL/CL/LCL lines.

    Args:
        series:    Dict of ``{series_name: [values]}``.  Each key becomes
                   a separate dataset.
        x_labels:  Labels for the x-axis (e.g. part names, subgroup IDs).
        title:     Chart title.
        ucl:       Upper Control Limit — drawn as a dashed red line.
        lcl:       Lower Control Limit — drawn as a dashed red line.
        cl:        Center Line — drawn as a solid grey line.
        y_label:   Y-axis label.
        canvas_id: HTML ``id`` for the canvas element.
        height_px: Chart wrapper height in pixels.
        op_colors: Per-series hex colors.

    Returns:
        HTML string with embedded ``<canvas>`` and ``<script>``.

    Example:
        >>> html = line_chart(
        ...     {"Op A": [0.01, 0.02, 0.01], "Op B": [0.02, 0.03, 0.01]},
        ...     x_labels=["P01", "P02", "P03"],
        ...     title="R-Chart",
        ...     ucl=0.05, cl=0.018,
        ... )
    """
    default_colors = ["#1A3A5C", "#E67E22", "#16A085", "#8E44AD", "#C0392B"]
    if op_colors is None:
        op_colors = default_colors

    datasets = []
    for idx, (name, vals) in enumerate(series.items()):
        c = op_colors[idx % len(op_colors)]
        datasets.append({
            "label": name,
            "data": [float(v) for v in vals],
            "borderColor": c,
            "backgroundColor": c + "22",
            "pointRadius": 5,
            "borderWidth": 1.5,
            "tension": 0.1,
        })

    if ucl is not None:
        datasets.append({
            "label": f"UCL = {ucl:.4f}",
            "data": [float(ucl)] * len(x_labels),
            "borderColor": "#C0392B",
            "borderDash": [6, 4],
            "borderWidth": 1.5,
            "pointRadius": 0,
            "fill": False,
        })
    if lcl is not None:
        datasets.append({
            "label": f"LCL = {lcl:.4f}",
            "data": [float(lcl)] * len(x_labels),
            "borderColor": "#C0392B",
            "borderDash": [6, 4],
            "borderWidth": 1.5,
            "pointRadius": 0,
            "fill": False,
        })
    if cl is not None:
        datasets.append({
            "label": f"CL = {cl:.4f}",
            "data": [float(cl)] * len(x_labels),
            "borderColor": "#95A5A6",
            "borderDash": [3, 3],
            "borderWidth": 1.2,
            "pointRadius": 0,
            "fill": False,
        })

    return f"""
<div class="card">
  <h2>{title}</h2>
  <div class="chart-wrap" style="height:{height_px}px">
    <canvas id="{canvas_id}"></canvas>
  </div>
</div>
<script>
(function() {{
  new Chart(document.getElementById('{canvas_id}'), {{
    type: 'line',
    data: {{
      labels: {json.dumps(list(x_labels))},
      datasets: {json.dumps(datasets)}
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{
        legend: {{position: 'bottom', labels: {{boxWidth: 12, font: {{size: 11}}}}}}
      }},
      scales: {{
        y: {{
          title: {{display: {'true' if y_label else 'false'}, text: {json.dumps(y_label)}}},
          ticks: {{font: {{size: 10}}}},
          grid: {{color: '#e8ecf0'}}
        }},
        x: {{grid: {{display: false}}, ticks: {{font: {{size: 10}}}}}}
      }}
    }}
  }});
}})();
</script>"""


def metrics_grid(
    kv_pairs: Sequence[Tuple[str, str, str, str]],
) -> str:
    """
    Return HTML for a 2-column KPI grid.

    Args:
        kv_pairs: List of ``(label, value, sub_text, color_css_var)`` tuples.
                  ``color_css_var`` is a CSS variable name like
                  ``"var(--green)"`` applied to the value text.

    Returns:
        HTML string for a ``<div class="kpi-grid">`` block.

    Example:
        >>> html = metrics_grid([
        ...     ("Cp",  "1.33", "Target >= 1.33", "var(--green)"),
        ...     ("Cpk", "1.28", "Min(upper/lower)", "var(--orange)"),
        ... ])
    """
    items = []
    for label, value, sub, color in kv_pairs:
        items.append(
            f'<div class="kpi">'
            f'<div class="kpi-label">{label}</div>'
            f'<div class="kpi-value" style="color:{color}">{value}</div>'
            f'<div class="kpi-sub">{sub}</div>'
            f'</div>'
        )
    return '<div class="kpi-grid">' + "\n".join(items) + "</div>"


def operator_toggles(
    operators: Sequence[str],
    colors: Optional[Sequence[str]] = None,
    chart_ids: Optional[Sequence[str]] = None,
) -> str:
    """
    Return HTML+JS for operator toggle buttons that show/hide chart datasets.

    Args:
        operators:  List of operator names.
        colors:     Per-operator hex colors (cycles through defaults if None).
        chart_ids:  Chart canvas IDs whose datasets will be toggled.

    Returns:
        HTML string with toggle buttons and inline JS.

    Example:
        >>> html = operator_toggles(["Alice", "Bob"], chart_ids=["r-chart"])
    """
    default_colors = ["#1A3A5C", "#E67E22", "#16A085", "#8E44AD", "#C0392B"]
    if colors is None:
        colors = [default_colors[i % len(default_colors)] for i in range(len(operators))]

    buttons = ""
    for i, (op, color) in enumerate(zip(operators, colors)):
        buttons += (
            f'<button class="op-btn" id="btn-{op}" '
            f'style="border-color:{color};color:{color}" '
            f'onclick="toggleOp(\'{op}\',{i})">'
            f"Operator {op}</button>\n"
        )

    charts_js = json.dumps(chart_ids or [])
    ops_js    = json.dumps(list(operators))

    return f"""
<div class="card" style="margin-bottom:18px">
  <h2>Operator Filter</h2>
  <div class="toggle-row">{buttons}</div>
</div>
<script>
(function() {{
  const _activeOps = new Set({ops_js});
  const _chartIds  = {charts_js};
  window.toggleOp = function(op, idx) {{
    if (_activeOps.has(op)) _activeOps.delete(op);
    else _activeOps.add(op);
    const btn = document.getElementById('btn-' + op);
    btn.classList.toggle('off', !_activeOps.has(op));
    _chartIds.forEach(id => {{
      const ch = Chart.getChart(id);
      if (!ch) return;
      {ops_js}.forEach((o, i) => ch.setDatasetVisibility(i, _activeOps.has(o)));
      ch.update();
    }});
  }};
}})();
</script>"""


def metrics_table_html(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    highlight_rows: Optional[Sequence[int]] = None,
) -> str:
    """
    Return an HTML ``<table>`` string.

    Args:
        headers:        Column header strings.
        rows:           Table body rows (each a list of cell strings).
        highlight_rows: 0-based indices of rows to apply ``class="hl"``
                        (bold font-weight).

    Returns:
        HTML string for a ``<table>`` element.

    Example:
        >>> html = metrics_table_html(
        ...     ["Component", "Value", "%TV"],
        ...     [["EV", "0.00872", "10.1%"], ["GRR", "0.01475", "17.0%"]],
        ...     highlight_rows=[1],
        ... )
    """
    highlight_rows = set(highlight_rows or [])
    ths = "".join(f"<th>{h}</th>" for h in headers)
    body_rows = []
    for i, row in enumerate(rows):
        cls = ' class="hl"' if i in highlight_rows else ""
        tds = "".join(f"<td>{cell}</td>" for cell in row)
        body_rows.append(f"<tr{cls}>{tds}</tr>")
    return (
        '<table><thead><tr>' + ths + '</tr></thead>'
        '<tbody>' + "\n".join(body_rows) + '</tbody></table>'
    )
