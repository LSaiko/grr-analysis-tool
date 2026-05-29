"""
msa_toolkit.anova
=================
Two-way crossed ANOVA for Gauge R&R studies (AIAG MSA 4th Edition).

The module implements the ``Part x Operator`` crossed design where every
operator measures every part ``r`` times.  It decomposes total variation
into:

  SS_total = SS_parts + SS_operators + SS_interaction + SS_error

and estimates the underlying variance components::

  sigma2_repeatability  (pure gauge noise)
  sigma2_operator       (systematic operator offsets)
  sigma2_interaction    (part-specific operator effects)
  sigma2_part           (true part-to-part variation)

p-values require ``scipy.stats.f`` which is imported with a try/except
guard so that the module remains usable without scipy (p-values will be
``None`` in that case).

Regulatory context: 21 CFR 820.72 (FDA QSR)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .report import (
    make_doc, make_header, make_footer, metrics_table,
    section_heading, embed_chart, para_style, NAVY, TEAL, ORANGE, GREEN, RED,
)
from .dashboard import (
    page_template, bar_chart, metrics_table_html, metrics_grid,
)

try:
    from scipy.stats import f as f_dist
    _SCIPY = True
except ImportError:
    _SCIPY = False

__all__ = [
    "AnovaResult",
    "two_way_anova",
    "variance_components",
    "print_anova_table",
    "build_anova_pdf",
    "build_anova_dashboard",
]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class AnovaResult:
    """
    Full results from a two-way crossed ANOVA.

    Attributes:
        n_parts:       Number of unique parts in the study.
        n_operators:   Number of unique operators.
        n_trials:      Number of replicated trials per cell.
        grand_mean:    Grand mean of all measurements.
        parts:         Sorted list of unique part identifiers.
        operators:     Sorted list of unique operator identifiers.

        ss_parts:       Sum of squares — parts (between-part variation).
        ss_operators:   Sum of squares — operators (between-operator).
        ss_interaction: Sum of squares — part × operator interaction.
        ss_error:       Sum of squares — within-cell error (repeatability).
        ss_total:       Total sum of squares.

        df_parts:       Degrees of freedom — parts.
        df_operators:   Degrees of freedom — operators.
        df_interaction: Degrees of freedom — interaction.
        df_error:       Degrees of freedom — error.
        df_total:       Total degrees of freedom.

        ms_parts:       Mean square — parts.
        ms_operators:   Mean square — operators.
        ms_interaction: Mean square — interaction.
        ms_error:       Mean square — error (= sigma2_repeatability estimate).

        f_parts:        F-ratio — parts.
        f_operators:    F-ratio — operators.
        f_interaction:  F-ratio — interaction.

        p_parts:        p-value — parts (None if scipy unavailable).
        p_operators:    p-value — operators (None if scipy unavailable).
        p_interaction:  p-value — interaction (None if scipy unavailable).
    """
    n_parts:       int   = 0
    n_operators:   int   = 0
    n_trials:      int   = 0
    grand_mean:    float = 0.0
    parts:         List  = field(default_factory=list)
    operators:     List  = field(default_factory=list)

    ss_parts:       float = 0.0
    ss_operators:   float = 0.0
    ss_interaction: float = 0.0
    ss_error:       float = 0.0
    ss_total:       float = 0.0

    df_parts:       int   = 0
    df_operators:   int   = 0
    df_interaction: int   = 0
    df_error:       int   = 0
    df_total:       int   = 0

    ms_parts:       float = 0.0
    ms_operators:   float = 0.0
    ms_interaction: float = 0.0
    ms_error:       float = 0.0

    f_parts:        float           = 0.0
    f_operators:    float           = 0.0
    f_interaction:  float           = 0.0

    p_parts:        Optional[float] = None
    p_operators:    Optional[float] = None
    p_interaction:  Optional[float] = None


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------

def two_way_anova(data: pd.DataFrame) -> AnovaResult:
    """
    Perform a two-way crossed ANOVA on balanced GR&R study data.

    The DataFrame must have columns ``Part``, ``Operator``, and
    ``Measurement`` (case-insensitive).  The study must be balanced:
    every operator measures every part the same number of times.

    Args:
        data: DataFrame with at minimum columns Part, Operator, Measurement.

    Returns:
        Populated :class:`AnovaResult` dataclass.

    Raises:
        ValueError: If required columns are missing or the design is
                    unbalanced.

    Example:
        >>> import pandas as pd
        >>> from msa_toolkit.anova import two_way_anova
        >>> df = pd.DataFrame({
        ...     "Part":        ["P1","P1","P1","P1","P2","P2","P2","P2"],
        ...     "Operator":    ["A","A","B","B","A","A","B","B"],
        ...     "Measurement": [10.1,10.2,10.0,10.1,10.5,10.4,10.3,10.4],
        ... })
        >>> result = two_way_anova(df)
    """
    # ── Normalise column names ─────────────────────────────────────────────
    col_map = {c.lower().strip(): c for c in data.columns}
    for req in ("part", "operator", "measurement"):
        if req not in col_map:
            raise ValueError(
                f"DataFrame must contain column '{req.capitalize()}'. "
                f"Found: {list(data.columns)}"
            )
    part_col  = col_map["part"]
    op_col    = col_map["operator"]
    meas_col  = col_map["measurement"]

    df = data[[part_col, op_col, meas_col]].copy()
    df.columns = ["Part", "Operator", "Measurement"]
    df["Measurement"] = pd.to_numeric(df["Measurement"])

    parts     = sorted(df["Part"].astype(str).unique())
    operators = sorted(df["Operator"].astype(str).unique())
    p = len(parts)
    o = len(operators)

    # ── Verify balanced design ─────────────────────────────────────────────
    cell_counts = (
        df.groupby(["Part", "Operator"])["Measurement"].count()
    )
    r_vals = cell_counts.values
    if r_vals.min() != r_vals.max():
        raise ValueError(
            "Unbalanced design: cell sizes vary. "
            f"Min={r_vals.min()}, Max={r_vals.max()}."
        )
    r = int(r_vals[0])
    n = p * o * r

    # ── Build cell-mean array  shape (p, o) ───────────────────────────────
    cell_means = np.zeros((p, o))
    for i, part in enumerate(parts):
        for j, op in enumerate(operators):
            vals = df[(df["Part"] == part) & (df["Operator"] == op)]["Measurement"].values
            cell_means[i, j] = vals.mean()

    grand_mean    = df["Measurement"].mean()
    part_means    = cell_means.mean(axis=1)    # shape (p,)
    op_means      = cell_means.mean(axis=0)    # shape (o,)

    # ── Sum of Squares ─────────────────────────────────────────────────────
    # SS_parts: between-part variation
    ss_parts = o * r * np.sum((part_means - grand_mean) ** 2)

    # SS_operators: between-operator variation
    ss_operators = p * r * np.sum((op_means - grand_mean) ** 2)

    # SS_interaction: part x operator interaction
    interaction_devs = (
        cell_means
        - part_means[:, np.newaxis]
        - op_means[np.newaxis, :]
        + grand_mean
    )
    ss_interaction = r * np.sum(interaction_devs ** 2)

    # SS_error: within-cell (repeatability)
    ss_error = 0.0
    for i, part in enumerate(parts):
        for j, op in enumerate(operators):
            vals = df[(df["Part"] == part) & (df["Operator"] == op)]["Measurement"].values
            ss_error += np.sum((vals - cell_means[i, j]) ** 2)

    ss_total = np.sum((df["Measurement"].values - grand_mean) ** 2)

    # ── Degrees of Freedom ────────────────────────────────────────────────
    df_parts       = p - 1
    df_operators   = o - 1
    df_interaction = (p - 1) * (o - 1)
    df_error       = p * o * (r - 1)
    df_total       = n - 1

    # ── Mean Squares ──────────────────────────────────────────────────────
    ms_parts       = ss_parts       / df_parts       if df_parts       > 0 else 0.0
    ms_operators   = ss_operators   / df_operators   if df_operators   > 0 else 0.0
    ms_interaction = ss_interaction / df_interaction if df_interaction > 0 else 0.0
    ms_error       = ss_error       / df_error       if df_error       > 0 else 0.0

    # ── F-ratios (each MS / MS_error) ────────────────────────────────────
    f_parts       = ms_parts       / ms_error if ms_error > 0 else 0.0
    f_operators   = ms_operators   / ms_error if ms_error > 0 else 0.0
    f_interaction = ms_interaction / ms_error if ms_error > 0 else 0.0

    # ── p-values (requires scipy) ─────────────────────────────────────────
    p_parts = p_operators = p_interaction = None
    if _SCIPY:
        p_parts       = float(f_dist.sf(f_parts,       df_parts,       df_error))
        p_operators   = float(f_dist.sf(f_operators,   df_operators,   df_error))
        p_interaction = float(f_dist.sf(f_interaction, df_interaction, df_error))

    return AnovaResult(
        n_parts=p, n_operators=o, n_trials=r,
        grand_mean=float(grand_mean),
        parts=parts, operators=operators,
        ss_parts=float(ss_parts),       ss_operators=float(ss_operators),
        ss_interaction=float(ss_interaction), ss_error=float(ss_error),
        ss_total=float(ss_total),
        df_parts=df_parts,             df_operators=df_operators,
        df_interaction=df_interaction, df_error=df_error, df_total=df_total,
        ms_parts=float(ms_parts),       ms_operators=float(ms_operators),
        ms_interaction=float(ms_interaction), ms_error=float(ms_error),
        f_parts=float(f_parts),         f_operators=float(f_operators),
        f_interaction=float(f_interaction),
        p_parts=p_parts, p_operators=p_operators, p_interaction=p_interaction,
    )


# ---------------------------------------------------------------------------
# Variance component decomposition
# ---------------------------------------------------------------------------

def variance_components(result: AnovaResult) -> Dict[str, float]:
    """
    Estimate variance components from an ANOVA result (EMS equations).

    Uses Expected Mean Square (EMS) equations for a balanced crossed
    two-way random model:

    - sigma2_repeatability = MS_error
    - sigma2_interaction   = max(0, (MS_interaction - MS_error) / r)
    - sigma2_operator      = max(0, (MS_operators - MS_interaction) / (p*r))
    - sigma2_part          = max(0, (MS_parts - MS_interaction) / (o*r))

    Negative estimates are clamped to zero (standard AIAG practice).

    Args:
        result: An :class:`AnovaResult` from :func:`two_way_anova`.

    Returns:
        Dict with keys ``sigma2_repeatability``, ``sigma2_interaction``,
        ``sigma2_operator``, ``sigma2_part``, and ``sigma2_total``.

    Example:
        >>> vc = variance_components(result)
        >>> print(f"Repeatability σ² = {vc['sigma2_repeatability']:.6f}")
    """
    p, o, r = result.n_parts, result.n_operators, result.n_trials

    s2_repeat  = result.ms_error
    s2_inter   = max(0.0, (result.ms_interaction - result.ms_error) / r)
    s2_op      = max(0.0, (result.ms_operators   - result.ms_interaction) / (p * r))
    s2_part    = max(0.0, (result.ms_parts       - result.ms_interaction) / (o * r))
    s2_total   = s2_repeat + s2_inter + s2_op + s2_part

    return {
        "sigma2_repeatability": s2_repeat,
        "sigma2_interaction":   s2_inter,
        "sigma2_operator":      s2_op,
        "sigma2_part":          s2_part,
        "sigma2_total":         s2_total,
    }


# ---------------------------------------------------------------------------
# Console table
# ---------------------------------------------------------------------------

def print_anova_table(result: AnovaResult) -> None:
    """
    Print a formatted two-way ANOVA table to stdout.

    Args:
        result: An :class:`AnovaResult` from :func:`two_way_anova`.

    Example:
        >>> print_anova_table(result)
    """
    w = 70
    print()
    print("=" * w)
    print("  TWO-WAY ANOVA  --  AIAG MSA 4th Edition (Crossed Design)".center(w))
    print("=" * w)
    print(f"  Design: {result.n_parts} parts x {result.n_operators} operators "
          f"x {result.n_trials} trials   Grand mean = {result.grand_mean:.5f}")
    print("-" * w)
    fmt = "  {:<16}  {:>10}  {:>4}  {:>10}  {:>8}  {:>8}"
    print(fmt.format("Source", "SS", "df", "MS", "F", "p-value"))
    print("  " + "-" * (w - 2))

    def pval(p):
        if p is None:
            return "  N/A  "
        if p < 0.0001:
            return "< 0.0001"
        return f"{p:.4f}"

    rows_data = [
        ("Parts",       result.ss_parts,       result.df_parts,
         result.ms_parts,       result.f_parts,       result.p_parts),
        ("Operators",   result.ss_operators,   result.df_operators,
         result.ms_operators,   result.f_operators,   result.p_operators),
        ("Interaction", result.ss_interaction, result.df_interaction,
         result.ms_interaction, result.f_interaction, result.p_interaction),
        ("Error",       result.ss_error,       result.df_error,
         result.ms_error,       None,                 None),
        ("Total",       result.ss_total,       result.df_total,
         None,                  None,                 None),
    ]
    for source, ss, df, ms, f, p in rows_data:
        ms_s = f"{ms:.6f}" if ms is not None else "    --    "
        f_s  = f"{f:.3f}"  if f  is not None else "  --  "
        p_s  = pval(p)     if p  is not None else "  --    "
        print(fmt.format(source, f"{ss:.6f}", df, ms_s, f_s, p_s))

    print("-" * w)
    vc = variance_components(result)
    print("  Variance Components:")
    for k, v in vc.items():
        label = k.replace("sigma2_", "sigma2 ").replace("_", " ").title()
        pct   = 100.0 * v / vc["sigma2_total"] if vc["sigma2_total"] > 0 else 0.0
        print(f"    {label:<30}  {v:.8f}  ({pct:.1f}%)")
    print("=" * w)
    print()


# ---------------------------------------------------------------------------
# PDF report
# ---------------------------------------------------------------------------

def build_anova_pdf(
    result: AnovaResult,
    output_path: Path,
    equipment: str = "Unspecified",
    study_operator: str = "Quality Engineering",
    title: str = "Two-Way ANOVA Report",
) -> None:
    """
    Generate a PDF ANOVA report with table and variance-component bar chart.

    Args:
        result:         An :class:`AnovaResult` from :func:`two_way_anova`.
        output_path:    Destination PDF path.
        equipment:      Gage / equipment identifier string.
        study_operator: Name of QE who performed the study.
        title:          Report title.

    Example:
        >>> build_anova_pdf(result, Path("anova_report.pdf"),
        ...                 equipment="CMM SN-001")
    """
    from reportlab.platypus import Spacer
    from datetime import date

    doc   = make_doc(output_path, title=title, author=study_operator)
    story = []

    story += make_header(
        title=title,
        metadata={
            "Equipment / Gage:": equipment,
            "Study Performed By:": study_operator,
            "Report Date:": str(date.today()),
            "Design:": (f"{result.n_parts} parts x {result.n_operators} "
                        f"operators x {result.n_trials} trials"),
            "Regulatory Reference:": "21 CFR 820.72  |  AIAG MSA 4th Edition",
        },
        subtitle="Crossed GR&R -- AIAG MSA 4th Edition",
    )

    # ── ANOVA table ────────────────────────────────────────────────────────
    story.append(section_heading("Two-Way ANOVA Table"))

    def pval_str(p):
        if p is None: return "N/A"
        if p < 0.0001: return "< 0.0001"
        return f"{p:.4f}"

    anova_rows = [
        ["Source", "SS", "df", "MS", "F", "p-value"],
        ["Parts",       f"{result.ss_parts:.6f}",       str(result.df_parts),
         f"{result.ms_parts:.6f}",       f"{result.f_parts:.3f}",
         pval_str(result.p_parts)],
        ["Operators",   f"{result.ss_operators:.6f}",   str(result.df_operators),
         f"{result.ms_operators:.6f}",   f"{result.f_operators:.3f}",
         pval_str(result.p_operators)],
        ["Interaction", f"{result.ss_interaction:.6f}", str(result.df_interaction),
         f"{result.ms_interaction:.6f}", f"{result.f_interaction:.3f}",
         pval_str(result.p_interaction)],
        ["Error",       f"{result.ss_error:.6f}",       str(result.df_error),
         f"{result.ms_error:.6f}",       "--", "--"],
        ["Total",       f"{result.ss_total:.6f}",       str(result.df_total),
         "--", "--", "--"],
    ]
    story.append(metrics_table(
        anova_rows,
        col_widths=[1.4, 1.2, 0.5, 1.2, 0.9, 1.0],
        highlight_rows=[(4, "#F4F6F8")],   # error row slight highlight
    ))
    story.append(Spacer(1, 0.12 * 72))

    # ── Variance components table ──────────────────────────────────────────
    story.append(section_heading("Estimated Variance Components"))
    vc = variance_components(result)
    vc_rows = [["Source", "Variance (sigma^2)", "Std Dev (sigma)", "% Total"]]
    for k, v in vc.items():
        if k == "sigma2_total":
            continue
        label = k.replace("sigma2_", "").replace("_", " ").title()
        pct   = 100.0 * v / vc["sigma2_total"] if vc["sigma2_total"] > 0 else 0.0
        vc_rows.append([label, f"{v:.8f}", f"{math.sqrt(v):.6f}", f"{pct:.1f}%"])
    vc_rows.append(["Total",
                    f"{vc['sigma2_total']:.8f}",
                    f"{math.sqrt(vc['sigma2_total']):.6f}", "100.0%"])

    story.append(metrics_table(vc_rows, col_widths=[1.9, 1.8, 1.6, 1.0]))
    story.append(Spacer(1, 0.12 * 72))

    # ── Variance component bar chart ───────────────────────────────────────
    story.append(section_heading("Variance Component Contributions (%)"))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    vc_plot = {k: v for k, v in vc.items() if k != "sigma2_total"}
    labels  = [k.replace("sigma2_", "").replace("_", "\n").title() for k in vc_plot]
    values  = [100.0 * v / vc["sigma2_total"] if vc["sigma2_total"] > 0 else 0.0
               for v in vc_plot.values()]
    bar_clrs = [TEAL, ORANGE, NAVY, "#8E44AD"][:len(labels)]

    fig, ax = plt.subplots(figsize=(7.0, 3.0), facecolor="white")
    bars = ax.bar(labels, values, color=bar_clrs, width=0.55, zorder=3)
    ax.set_ylabel("% of Total Variance", fontsize=9)
    ax.set_title("Variance Component Breakdown", fontsize=10, fontweight="bold", pad=8)
    ax.set_ylim(0, max(values) * 1.25 + 5)
    ax.yaxis.grid(True, linestyle=":", alpha=0.5, zorder=0)
    ax.set_axisbelow(True)
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                f"{val:.1f}%", ha="center", va="bottom", fontsize=8.5,
                fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    story += embed_chart(fig, 6.8, 3.0)

    story += make_footer()
    doc.build(story)
    print(f"[+] ANOVA PDF written to: {output_path}")


# ---------------------------------------------------------------------------
# HTML dashboard
# ---------------------------------------------------------------------------

def build_anova_dashboard(
    result: AnovaResult,
    output_path: Path,
    equipment: str = "Unspecified",
    study_operator: str = "Quality Engineering",
    title: str = "ANOVA Dashboard",
    version: str = "0.1.0",
) -> None:
    """
    Generate a self-contained interactive HTML ANOVA dashboard.

    Args:
        result:         An :class:`AnovaResult` from :func:`two_way_anova`.
        output_path:    Destination HTML path.
        equipment:      Gage / equipment identifier.
        study_operator: Study QE name.
        title:          Dashboard title.
        version:        msa_toolkit version string embedded in footer.

    Example:
        >>> build_anova_dashboard(result, Path("anova_dashboard.html"))
    """
    from datetime import date

    vc = variance_components(result)
    vc_items = [(k, v) for k, v in vc.items() if k != "sigma2_total"]

    # ── KPI grid ──────────────────────────────────────────────────────────
    kpi_items = [
        ("MS Error (Repeatability)", f"{result.ms_error:.6f}", "Pure gauge noise variance", "var(--teal)"),
        ("MS Parts",   f"{result.ms_parts:.6f}",
         f"F = {result.f_parts:.2f}  p = {result.p_parts:.4f}" if result.p_parts is not None else f"F = {result.f_parts:.2f}",
         "var(--navy)"),
        ("MS Operators", f"{result.ms_operators:.6f}",
         f"F = {result.f_operators:.2f}  p = {result.p_operators:.4f}" if result.p_operators is not None else f"F = {result.f_operators:.2f}",
         "var(--orange)"),
        ("MS Interaction", f"{result.ms_interaction:.6f}",
         f"F = {result.f_interaction:.2f}  p = {result.p_interaction:.4f}" if result.p_interaction is not None else f"F = {result.f_interaction:.2f}",
         "var(--grey)"),
    ]
    kpi_html = f'<div class="card" style="margin-bottom:18px"><h2>Key Mean Squares</h2>{metrics_grid(kpi_items)}</div>'

    # ── ANOVA table ────────────────────────────────────────────────────────
    def pstr(p):
        if p is None: return "N/A"
        if p < 0.0001: return "&lt; 0.0001"
        return f"{p:.4f}"

    anova_tbl = metrics_table_html(
        ["Source", "SS", "df", "MS", "F", "p-value"],
        [
            ["Parts",       f"{result.ss_parts:.6f}",       str(result.df_parts),
             f"{result.ms_parts:.6f}",       f"{result.f_parts:.3f}", pstr(result.p_parts)],
            ["Operators",   f"{result.ss_operators:.6f}",   str(result.df_operators),
             f"{result.ms_operators:.6f}",   f"{result.f_operators:.3f}", pstr(result.p_operators)],
            ["Interaction", f"{result.ss_interaction:.6f}", str(result.df_interaction),
             f"{result.ms_interaction:.6f}", f"{result.f_interaction:.3f}", pstr(result.p_interaction)],
            ["Error",       f"{result.ss_error:.6f}",       str(result.df_error),
             f"{result.ms_error:.6f}",       "--", "--"],
            ["Total",       f"{result.ss_total:.6f}",       str(result.df_total),
             "--", "--", "--"],
        ],
        highlight_rows=[4],
    )

    # ── Variance components chart ──────────────────────────────────────────
    vc_labels = [k.replace("sigma2_", "").replace("_", " ").title() for k, _ in vc_items]
    vc_vals   = [100.0 * v / vc["sigma2_total"] if vc["sigma2_total"] > 0 else 0.0
                 for _, v in vc_items]
    vc_colors = ["#16A085", "#E67E22", "#1A3A5C", "#8E44AD"]

    vc_chart   = bar_chart(vc_labels, vc_vals, "Variance Components (% Total)",
                           bar_colors=vc_colors[:len(vc_labels)],
                           y_label="% Total Variance", canvas_id="vc-chart")
    anova_card = f'<div class="card" style="margin-bottom:18px"><h2>ANOVA Table</h2>{anova_tbl}</div>'

    body = (
        kpi_html
        + '<div class="grid grid-2" style="margin-bottom:18px">'
        + vc_chart
        + f'</div>'
        + anova_card
    )

    html = page_template(
        title=title,
        body_html=body,
        metadata={
            "Equipment": equipment,
            "Study by": study_operator,
        },
        version=version,
    )
    output_path.write_text(html, encoding="utf-8")
    print(f"[+] ANOVA dashboard written to: {output_path}")
