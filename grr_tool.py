"""
grr_tool.py  --  Gauge Repeatability & Reproducibility (GR&R) Analysis Tool
=============================================================================
Follows AIAG Measurement Systems Analysis (MSA) 4th Edition methodology.
Intended use: Medical device manufacturing quality engineering.
Regulatory context: 21 CFR 820.72 -- Inspection, Measuring, and Test Equipment.

Author note:
    This tool automates the AIAG crossed GR&R study, the industry-standard
    method for evaluating measurement system variation in manufacturing
    environments. It separates total measurement variation into:
      - Equipment Variation (EV): repeatability -- variation within one operator
      - Appraiser Variation (AV): reproducibility -- variation between operators
      - Part Variation (PV): actual part-to-part variation
    The goal is to confirm the measurement system's error is small relative
    to total variation before using it for product acceptance decisions.

CSV format  (wide layout -- one row per operator+part combination):
    Part,Operator,Trial1,Trial2[,Trial3[,...]]
    P01,Alice,10.002,10.005,10.001
    P01,Bob,10.004,9.998,10.003
    ...

Usage examples:
    # Generate sample data and run full analysis (PDF + dashboard):
    python grr_tool.py --generate-sample --input sample_grr.csv \\
        --output grr_report.pdf --dashboard grr_dashboard.html \\
        --equipment "Mitutoyo 293-340-30" --operator "J. Martinez"

    # Existing CSV, PDF only, with tolerance:
    python grr_tool.py --input my_data.csv --output report.pdf \\
        --tolerance 0.050 --equipment "Digital Caliper #3"

    # Dashboard only (no PDF):
    python grr_tool.py --input my_data.csv --dashboard results.html
"""

from __future__ import annotations

__version__ = "1.1.0"

import argparse
import csv
import json
import math
import random
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# AIAG MSA 4th Edition Constants  (5.15-sigma study variation convention)
# ---------------------------------------------------------------------------
# K1: control chart constant for within-operator range variation.
#   EV = R-bar-bar * K1  where K1 = 5.15 / d2*(trials)
#   For 3 trials: K1 = 5.15 / 1.6926 = 3.05
K1_BY_TRIALS: Dict[int, float] = {2: 4.56, 3: 3.05, 4: 2.50, 5: 2.21}

# K2: constant for appraiser variation, based on number of operators.
#   K2 = 5.15 / d2*(operators)
K2_BY_OPERATORS: Dict[int, float] = {2: 3.65, 3: 2.70, 4: 2.30, 5: 2.08}

# K3: constant for part variation, based on number of parts.
#   K3 = 5.15 / d2*(parts)
K3_BY_PARTS: Dict[int, float] = {
    2: 3.65, 3: 2.70, 4: 2.30, 5: 2.08,
    6: 1.93, 7: 1.82, 8: 1.74, 9: 1.67, 10: 1.62,
}

# D4: upper control limit multiplier for R-charts (keyed on trials)
D4_BY_TRIALS: Dict[int, float] = {2: 3.267, 3: 2.574, 4: 2.282, 5: 2.114}

# Acceptance thresholds per AIAG MSA 4th Ed., Section III
GRR_ACCEPTABLE_THRESHOLD = 10.0   # %GR&R <= 10% -> Acceptable
GRR_MARGINAL_THRESHOLD   = 30.0   # %GR&R <= 30% -> Marginal
NDC_MINIMUM              = 5      # ndc >= 5 required for adequate discrimination

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
NAVY   = "#1A3A5C"
TEAL   = "#16A085"
ORANGE = "#E67E22"
GREEN  = "#27AE60"
RED    = "#C0392B"
GREY   = "#95A5A6"
_OP_COLORS  = [NAVY, ORANGE, TEAL, "#8E44AD", RED]
_OP_MARKERS = ["o", "s", "^", "D", "v"]

# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class MeasurementRecord:
    """Represents one row of GR&R study data (one operator x one part)."""
    part:     str
    operator: str
    trials:   List[float]   # length == number of trials

    @property
    def mean(self) -> float:
        return sum(self.trials) / len(self.trials)

    @property
    def range_(self) -> float:
        return max(self.trials) - min(self.trials)


@dataclass
class OperatorStats:
    """Per-operator summary statistics used in AIAG calculations."""
    name:        str
    part_ranges: List[float]   # range of each part's trials for this operator
    part_means:  List[float]   # mean of each part's trials for this operator
    r_bar:       float = 0.0   # R-bar = average range across all parts
    x_bar:       float = 0.0   # X-bar = grand mean for this operator

    def __post_init__(self):
        self.r_bar = sum(self.part_ranges) / len(self.part_ranges)
        self.x_bar = sum(self.part_means)  / len(self.part_means)


@dataclass
class GRRResults:
    """All computed GR&R metrics per AIAG MSA 4th Edition."""
    # Raw intermediate values (for audit trail)
    grand_mean:  float = 0.0
    r_bar_bar:   float = 0.0   # average of all operator R-bars
    x_diff:      float = 0.0   # max(op mean) - min(op mean)
    rp:          float = 0.0   # range of part averages
    ucl_r:       float = 0.0   # upper control limit for ranges
    k1:          float = 0.0
    k2:          float = 0.0
    k3:          float = 0.0
    d4:          float = 0.0
    n_parts:     int   = 0
    n_operators: int   = 0
    n_trials:    int   = 0

    # Variance components (5.15-sigma study variation)
    ev:  float = 0.0   # Equipment Variation (repeatability)
    av:  float = 0.0   # Appraiser Variation (reproducibility)
    grr: float = 0.0   # Combined GR&R
    pv:  float = 0.0   # Part Variation
    tv:  float = 0.0   # Total Variation

    # Percentage contributions (%Study Variation)
    pct_ev:  float = 0.0
    pct_av:  float = 0.0
    pct_grr: float = 0.0
    pct_pv:  float = 0.0

    # Optional tolerance-based metrics
    tolerance:   Optional[float] = None
    pct_tol_ev:  Optional[float] = None
    pct_tol_av:  Optional[float] = None
    pct_tol_grr: Optional[float] = None

    # Quality indicator
    ndc:        int  = 0       # Number of Distinct Categories (floor integer)
    av_clamped: bool = False   # True when AV^2 < 0 and was clamped to 0
    status:     str  = ""      # ACCEPTABLE / MARGINAL / UNACCEPTABLE

    # Per-operator breakdown (for tables and charts)
    parts:          List[str]           = field(default_factory=list)
    operator_stats: List[OperatorStats] = field(default_factory=list)
    out_of_control: List[Tuple]         = field(default_factory=list)

    @property
    def verdict_color_hex(self) -> str:
        return {
            "ACCEPTABLE":   GREEN,
            "MARGINAL":     ORANGE,
            "UNACCEPTABLE": RED,
        }.get(self.status, "#555555")


# ---------------------------------------------------------------------------
# Sample Data Generator
# ---------------------------------------------------------------------------

def generate_sample_data(output_path: Path) -> None:
    """
    Generate a realistic 10-part x 3-operator x 3-trial GR&R dataset
    and write it to a CSV file (wide format: Part, Operator, Trial1..3).

    Measurement model:
        measurement = true_part_value + operator_bias + gaussian_noise
    """
    random.seed(42)
    nominal    = 10.000   # mm -- arbitrary nominal dimension
    true_vals  = [round(nominal + random.uniform(-0.03, 0.03), 4) for _ in range(10)]
    op_biases  = {"Alice": 0.0, "Bob": 0.003, "Carol": -0.002}
    noise_sig  = 0.002    # mm repeatability sigma
    parts      = [f"P{i+1:02d}" for i in range(10)]
    operators  = list(op_biases.keys())

    rows = [["Part", "Operator", "Trial1", "Trial2", "Trial3"]]
    for part_name, true_val in zip(parts, true_vals):
        for op in operators:
            b  = op_biases[op]
            t1 = round(true_val + b + random.gauss(0, noise_sig), 4)
            t2 = round(true_val + b + random.gauss(0, noise_sig), 4)
            t3 = round(true_val + b + random.gauss(0, noise_sig), 4)
            rows.append([part_name, op, t1, t2, t3])

    with open(output_path, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    print(f"[+] Sample data written to: {output_path}")


# ---------------------------------------------------------------------------
# Data Loading & Validation
# ---------------------------------------------------------------------------

def load_data(csv_path: Path) -> Tuple[List[MeasurementRecord], int, int, int]:
    """
    Load and validate GR&R study data from a wide-format CSV file.

    Expected columns: Part, Operator, Trial1, Trial2[, Trial3[, ...]]
    At minimum Trial1 and Trial2 must be present (2 trials minimum).

    Returns:
        Tuple of (records, n_parts, n_operators, n_trials).

    Raises:
        SystemExit on validation failure.
    """
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        sys.exit(f"[ERROR] Input file not found: {csv_path}")
    except Exception as exc:
        sys.exit(f"[ERROR] Failed to read CSV: {exc}")

    # Normalise column names for matching (preserve original for display)
    col_map    = {c.lower().strip(): c for c in df.columns}
    trial_cols = [col_map[k] for k in sorted(col_map) if k.startswith("trial")]

    if len(trial_cols) < 2:
        sys.exit("[ERROR] CSV must contain at least Trial1 and Trial2 columns.")

    for req in ("part", "operator"):
        if req not in col_map:
            sys.exit(f"[ERROR] Missing required column: '{req.capitalize()}'")

    part_col = col_map["part"]
    op_col   = col_map["operator"]

    for col in trial_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if df[trial_cols].isna().any().any():
        sys.exit("[ERROR] Non-numeric values found in trial columns.")

    records = [
        MeasurementRecord(
            part=str(row[part_col]),
            operator=str(row[op_col]),
            trials=[float(row[c]) for c in trial_cols],
        )
        for _, row in df.iterrows()
    ]

    parts       = sorted(df[part_col].astype(str).unique())
    operators   = sorted(df[op_col].astype(str).unique())
    n_parts     = len(parts)
    n_operators = len(operators)
    n_trials    = len(trial_cols)

    if n_trials not in K1_BY_TRIALS:
        sys.exit(f"[ERROR] Unsupported trial count {n_trials}. "
                 f"Supported: {sorted(K1_BY_TRIALS)}")
    if n_operators not in K2_BY_OPERATORS:
        sys.exit(f"[ERROR] Unsupported operator count {n_operators}. "
                 f"Supported: {sorted(K2_BY_OPERATORS)}")
    if n_parts not in K3_BY_PARTS:
        sys.exit(f"[ERROR] Unsupported part count {n_parts}. "
                 f"Supported: {sorted(K3_BY_PARTS)}")

    print(f"[+] Loaded {len(records)} records: "
          f"{n_parts} parts x {n_operators} operators x {n_trials} trials")
    return records, n_parts, n_operators, n_trials


# ---------------------------------------------------------------------------
# GR&R Calculations  (AIAG MSA 4th Edition -- Average & Range Method)
# ---------------------------------------------------------------------------

def compute_grr(
    records:     List[MeasurementRecord],
    n_parts:     int,
    n_operators: int,
    n_trials:    int,
    tolerance:   Optional[float] = None,
) -> GRRResults:
    """
    Perform the full AIAG crossed GR&R calculation.

    AIAG Method Overview
    --------------------
    Study variation is expressed as 5.15-sigma (covers 99% of a normal
    distribution). All components are in those units, then expressed as
    percentages of total variation for acceptance evaluation.

    Steps:
      1. Build per-operator statistics (R-bar, X-bar per operator)
      2. Compute R-bar-bar (grand average range -> repeatability source)
      3. Compute X_diff (operator mean spread -> reproducibility source)
      4. Apply K constants to convert ranges to 5.15-sigma study variation
      5. Propagate through variance equations to get TV
      6. Compute percentage contributions, NDC, and acceptance status
    """
    res = GRRResults(
        n_parts=n_parts, n_operators=n_operators, n_trials=n_trials,
        tolerance=tolerance,
        k1=K1_BY_TRIALS[n_trials],
        k2=K2_BY_OPERATORS[n_operators],
        k3=K3_BY_PARTS[n_parts],
        d4=D4_BY_TRIALS[n_trials],
    )
    k1, k2, k3, d4 = res.k1, res.k2, res.k3, res.d4

    # -- STEP 1: Per-operator statistics -----------------------------------
    operator_map: Dict[str, List[MeasurementRecord]] = {}
    for rec in records:
        operator_map.setdefault(rec.operator, []).append(rec)

    op_stats: List[OperatorStats] = []
    for op_name in sorted(operator_map):
        op_recs     = operator_map[op_name]
        part_ranges = [r.range_ for r in op_recs]
        part_means  = [r.mean   for r in op_recs]
        op_stats.append(OperatorStats(
            name=op_name,
            part_ranges=part_ranges,
            part_means=part_means,
        ))
    res.operator_stats = op_stats

    # -- STEP 2: R-bar-bar (equipment / repeatability source) ---------------
    r_bars        = [op.r_bar for op in op_stats]
    res.r_bar_bar = sum(r_bars) / len(r_bars)
    res.ucl_r     = d4 * res.r_bar_bar

    # Identify out-of-control ranges
    parts = sorted({rec.part for rec in records})
    res.parts = parts
    for i, op in enumerate(op_stats):
        for j, (part, rng) in enumerate(zip(parts, op.part_ranges)):
            if rng > res.ucl_r:
                res.out_of_control.append((op.name, part, rng))

    # -- STEP 3: X_diff (operator mean spread -> reproducibility) -----------
    op_means   = [op.x_bar for op in op_stats]
    res.x_diff = max(op_means) - min(op_means)

    # -- STEP 4: Grand mean and part range ----------------------------------
    all_vals       = [t for rec in records for t in rec.trials]
    res.grand_mean = sum(all_vals) / len(all_vals)

    part_map: Dict[str, List[MeasurementRecord]] = {}
    for rec in records:
        part_map.setdefault(rec.part, []).append(rec)

    part_averages = [
        sum(r.mean for r in part_map[p]) / len(part_map[p])
        for p in parts
    ]
    res.rp = max(part_averages) - min(part_averages)

    # -- STEP 5: Variance components ----------------------------------------
    # EV (Equipment Variation / Repeatability)
    res.ev = res.r_bar_bar * k1

    # AV (Appraiser Variation / Reproducibility)
    av_sq = (res.x_diff * k2) ** 2 - (res.ev ** 2 / (n_parts * n_trials))
    if av_sq < 0:
        res.av_clamped = True
    res.av = math.sqrt(max(0.0, av_sq))

    # GR&R, PV, TV
    res.grr = math.sqrt(res.ev ** 2 + res.av ** 2)
    res.pv  = res.rp * k3
    res.tv  = math.sqrt(res.grr ** 2 + res.pv ** 2)

    # -- STEP 6: Percentage contributions and acceptance --------------------
    if res.tv > 0:
        res.pct_ev  = (res.ev  / res.tv) * 100
        res.pct_av  = (res.av  / res.tv) * 100
        res.pct_grr = (res.grr / res.tv) * 100
        res.pct_pv  = (res.pv  / res.tv) * 100

    # NDC -- Number of Distinct Categories (AIAG specifies floor integer)
    res.ndc = int(math.floor(1.41 * res.pv / res.grr)) if res.grr > 0 else 0

    if res.pct_grr <= GRR_ACCEPTABLE_THRESHOLD:
        res.status = "ACCEPTABLE"
    elif res.pct_grr <= GRR_MARGINAL_THRESHOLD:
        res.status = "MARGINAL"
    else:
        res.status = "UNACCEPTABLE"

    # Optional %Tolerance metrics
    if tolerance and tolerance > 0:
        res.pct_tol_ev  = 100.0 * res.ev  / tolerance
        res.pct_tol_av  = 100.0 * res.av  / tolerance
        res.pct_tol_grr = 100.0 * res.grr / tolerance

    return res


# ---------------------------------------------------------------------------
# Console Report
# ---------------------------------------------------------------------------

def print_console_report(res: GRRResults, equipment: str, study_operator: str) -> None:
    """Print a formatted summary to stdout."""
    w = 62
    print()
    print("=" * w)
    print("  GR&R STUDY RESULTS  --  AIAG MSA 4th Edition".center(w))
    print("=" * w)
    print(f"  Equipment : {equipment}")
    print(f"  Performed : {study_operator}")
    print(f"  Date      : {date.today()}")
    print("-" * w)
    print(f"  Grand Mean   : {res.grand_mean:.4f}")
    print(f"  R-bar-bar    : {res.r_bar_bar:.4f}")
    print(f"  X-diff       : {res.x_diff:.4f}")
    print(f"  Rp           : {res.rp:.4f}")
    print(f"  UCL_R        : {res.ucl_r:.4f}")
    print("-" * w)
    print(f"  {'Component':<28} {'Study Var':>10}  {'%TV':>7}")
    print(f"  {'-' * 50}")
    rows = [
        ("EV  (Repeatability)",   res.ev,  res.pct_ev),
        ("AV  (Reproducibility)", res.av,  res.pct_av),
        ("GR&R (Combined)",       res.grr, res.pct_grr),
        ("PV  (Part Variation)",  res.pv,  res.pct_pv),
        ("TV  (Total Variation)", res.tv,  100.0),
    ]
    for label, sv, p in rows:
        print(f"  {label:<28} {sv:>10.5f}  {p:>6.1f}%")

    print(f"\n  NDC (Distinct Categories): {res.ndc}")

    if res.tolerance:
        print(f"\n  %Tolerance  EV  : {res.pct_tol_ev:.1f}%")
        print(f"  %Tolerance  AV  : {res.pct_tol_av:.1f}%")
        print(f"  %Tolerance  GRR : {res.pct_tol_grr:.1f}%")

    if res.av_clamped:
        print("\n  NOTE: AV^2 was negative -- AV set to 0.")
        print("        Operator variation is not distinguishable from gauge noise.")

    if res.out_of_control:
        print(f"\n  WARNING: {len(res.out_of_control)} range(s) exceeded "
              f"UCL_R ({res.ucl_r:.4f}) -- investigate before accepting results.")

    print("-" * w)
    print(f"  STATUS: {res.status}")
    print(f"  (%GRR = {res.pct_grr:.1f}% | <=10% Acceptable  10-30% Marginal  >30% Unacceptable)")
    print("=" * w)
    print()


# ---------------------------------------------------------------------------
# Matplotlib Charts  (embedded as PNG in PDF)
# ---------------------------------------------------------------------------

def _fig_to_image(fig: plt.Figure, w_in: float, h_in: float) -> Image:
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    img = Image(buf, width=w_in * inch, height=h_in * inch)
    plt.close(fig)
    return img


def _chart_components(res: GRRResults) -> Image:
    """Bar chart of variance component %Study Variation."""
    labels = ["Repeatability\n(EV)", "Reproducibility\n(AV)",
              "Gauge R&R\n(GRR)", "Part Variation\n(PV)"]
    values = [res.pct_ev, res.pct_av, res.pct_grr, res.pct_pv]
    bar_colors = [
        TEAL, ORANGE,
        RED if res.pct_grr > 30 else ORANGE if res.pct_grr > 10 else GREEN,
        NAVY,
    ]
    fig, ax = plt.subplots(figsize=(7.0, 3.2), facecolor="white")
    bars = ax.bar(labels, values, color=bar_colors, width=0.55, zorder=3)
    ax.axhline(10, color=GREEN, linestyle="--", linewidth=1.3,
               label="10% (Acceptable)", zorder=4)
    ax.axhline(30, color=RED,   linestyle="--", linewidth=1.3,
               label="30% (Unacceptable)", zorder=4)
    ax.set_ylabel("% Study Variation", fontsize=9)
    ax.set_title("Variance Component Contributions", fontsize=10,
                 fontweight="bold", pad=8)
    ax.set_ylim(0, max(max(values) * 1.25, 36))
    ax.yaxis.grid(True, linestyle=":", alpha=0.5, zorder=0)
    ax.set_axisbelow(True)
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.6,
                f"{val:.1f}%", ha="center", va="bottom",
                fontsize=8.5, fontweight="bold")
    ax.legend(fontsize=7.5, loc="upper right")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return _fig_to_image(fig, 6.8, 3.2)


def _chart_range(res: GRRResults) -> Image:
    """R-Chart (range by part and operator)."""
    parts  = res.parts
    part_x = np.arange(1, len(parts) + 1)
    p_lbl  = [p.lstrip("P0") or p for p in parts]

    fig, ax = plt.subplots(figsize=(6.8, 2.6), facecolor="white")
    for i, op in enumerate(res.operator_stats):
        ax.plot(part_x, op.part_ranges,
                marker=_OP_MARKERS[i % 5], color=_OP_COLORS[i % 5],
                linewidth=1.2, markersize=5, label=f"Op. {op.name}", zorder=3)
    ax.axhline(res.ucl_r,     color=RED,  linestyle="--", linewidth=1.3,
               label=f"UCL_R = {res.ucl_r:.4f}", zorder=4)
    ax.axhline(res.r_bar_bar, color=GREY, linestyle="-",  linewidth=1.0,
               label=f"R-bar = {res.r_bar_bar:.4f}", zorder=3)
    ax.set_xlabel("Part", fontsize=9)
    ax.set_ylabel("Range", fontsize=9)
    ax.set_title("Range Chart (R-Chart) by Operator", fontsize=10,
                 fontweight="bold", pad=8)
    ax.set_xticks(part_x)
    ax.set_xticklabels(p_lbl, fontsize=8)
    ax.yaxis.grid(True, linestyle=":", alpha=0.5)
    ax.set_axisbelow(True)
    ax.legend(fontsize=7.5, ncol=min(res.n_operators + 2, 6))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return _fig_to_image(fig, 6.8, 2.6)


def _chart_xbar(res: GRRResults) -> Image:
    """X-bar Chart (mean by part and operator)."""
    parts  = res.parts
    part_x = np.arange(1, len(parts) + 1)
    p_lbl  = [p.lstrip("P0") or p for p in parts]

    fig, ax = plt.subplots(figsize=(6.8, 2.6), facecolor="white")
    for i, op in enumerate(res.operator_stats):
        ax.plot(part_x, op.part_means,
                marker=_OP_MARKERS[i % 5], color=_OP_COLORS[i % 5],
                linewidth=1.2, markersize=5, label=f"Op. {op.name}", zorder=3)
    ax.set_xlabel("Part", fontsize=9)
    ax.set_ylabel("Measurement", fontsize=9)
    ax.set_title("Average Chart (X-bar Chart) -- Mean by Part and Operator",
                 fontsize=10, fontweight="bold", pad=8)
    ax.set_xticks(part_x)
    ax.set_xticklabels(p_lbl, fontsize=8)
    ax.yaxis.grid(True, linestyle=":", alpha=0.5)
    ax.set_axisbelow(True)
    ax.legend(fontsize=7.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return _fig_to_image(fig, 6.8, 2.6)


# ---------------------------------------------------------------------------
# PDF Report
# ---------------------------------------------------------------------------

_C_DARK  = colors.HexColor(NAVY)
_C_MID   = colors.HexColor("#2E6DA4")
_C_LGRAY = colors.HexColor("#F0F4F8")
_C_BORD  = colors.HexColor("#C5D3E0")
_C_WHITE = colors.white
_C_BLACK = colors.black


def _ps(name: str, **kw) -> ParagraphStyle:
    defaults = dict(fontName="Helvetica", fontSize=9, spaceAfter=4)
    defaults.update(kw)
    return ParagraphStyle(name, **defaults)


def build_pdf_report(
    res:            GRRResults,
    output_path:    Path,
    equipment:      str,
    study_operator: str,
    title:          str = "GR&R Study Report",
) -> None:
    """
    Generate a professional GR&R study PDF report using ReportLab Platypus.

    Sections:
      1. Title block with study metadata
      2. Variation Components table (% Study Variation)
      3. Intermediate Calculation Values (audit trail)
      4. Per-Operator Breakdown table
      5. Acceptance determination banner (color-coded)
      6. AIAG acceptance criteria reference table
      7. Control charts (Components bar, R-Chart, X-bar Chart)
      8. Footer with regulatory citations
    """
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.65 * inch,  bottomMargin=0.80 * inch,
        title=title,
        author=study_operator,
        subject="Gauge R&R Study -- AIAG MSA 4th Edition",
    )

    s_title   = _ps("T",  fontSize=16, fontName="Helvetica-Bold",
                          textColor=_C_DARK, alignment=1, spaceAfter=3)
    s_sub     = _ps("Su", fontSize=8.5, textColor=colors.HexColor("#555555"),
                          alignment=1, spaceAfter=10)
    s_section = _ps("Se", fontSize=10.5, fontName="Helvetica-Bold",
                          textColor=_C_DARK, spaceBefore=8, spaceAfter=4)
    s_note    = _ps("N",  fontSize=7.5, fontName="Helvetica-Oblique",
                          textColor=colors.HexColor("#666666"), spaceAfter=3)
    s_warn    = _ps("W",  fontSize=8.5, textColor=colors.HexColor(RED))
    s_body    = _ps("B",  fontSize=8.5)
    s_verdict = _ps("V",  fontSize=11, fontName="Helvetica-Bold",
                          textColor=colors.white, alignment=1)
    s_footer  = _ps("F",  fontSize=6.5, fontName="Helvetica-Oblique",
                          textColor=colors.HexColor("#888888"), spaceBefore=4)

    hr_heavy = HRFlowable(width="100%", thickness=1.5, color=_C_DARK)
    hr_light = HRFlowable(width="100%", thickness=0.5, color=_C_BORD)

    story = []

    # ---- Title & metadata ------------------------------------------------
    story += [
        Paragraph(title, s_title),
        Paragraph(
            f"Gauge Repeatability &amp; Reproducibility -- AIAG MSA 4th Edition "
            f"&nbsp;|&nbsp; "
            f"{res.n_parts} Parts &nbsp;|&nbsp; "
            f"{res.n_operators} Operators &nbsp;|&nbsp; "
            f"{res.n_trials} Trials",
            s_sub,
        ),
        hr_heavy,
        Spacer(1, 0.10 * inch),
    ]

    meta_rows = [
        ["Equipment / Gage:", equipment],
        ["Study Performed By:", study_operator],
        ["Report Date:", str(date.today())],
        ["Study Design:", f"{res.n_operators} Operators, AIAG Crossed GR&R"],
        ["Regulatory Reference:", "21 CFR 820.72  |  AIAG MSA 4th Edition"],
    ]
    meta_tbl = Table(meta_rows, colWidths=[1.9 * inch, 5.1 * inch])
    meta_tbl.setStyle(TableStyle([
        ("FONTNAME",  (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",  (0, 0), (-1, -1), 8.5),
        ("LEADING",   (0, 0), (-1, -1), 13),
        ("TEXTCOLOR", (0, 0), (0, -1), _C_DARK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story += [meta_tbl, Spacer(1, 0.12 * inch)]

    # ---- Variation Components table --------------------------------------
    story.append(Paragraph("Variation Components (%Study Variation)", s_section))

    def _verdict(p: float) -> str:
        if p <= 10: return "Acceptable"
        if p <= 30: return "Marginal"
        return "Unacceptable"

    def _level(p: float) -> str:
        if p <= 10: return "Low"
        if p <= 30: return "Moderate"
        return "High"

    vc_header = ["Component", "Study Variation", "% of TV", "Assessment"]
    vc_data = [
        ("EV -- Equipment (Repeatability)",   res.ev,  res.pct_ev,  _level(res.pct_ev)),
        ("AV -- Appraiser (Reproducibility)", res.av,  res.pct_av,  _level(res.pct_av)),
        ("GR&R -- Combined",                  res.grr, res.pct_grr, _verdict(res.pct_grr)),
        ("PV -- Part Variation",              res.pv,  res.pct_pv,  "--"),
        ("TV -- Total Variation",             res.tv,  100.0,        "--"),
    ]
    vc_rows = [vc_header]
    for label, sv, p, interp in vc_data:
        vc_rows.append([label, f"{sv:.5f}", f"{p:.1f}%", interp])

    if res.tolerance:
        vc_rows.append(["", "", "", ""])
        for label, val in [
            ("%Tolerance (EV)",  res.pct_tol_ev  or 0),
            ("%Tolerance (AV)",  res.pct_tol_av  or 0),
            ("%Tolerance (GRR)", res.pct_tol_grr or 0),
        ]:
            vc_rows.append([label, "--", f"{val:.1f}%", _verdict(val)])

    GRR_ROW = 3   # header=0, EV=1, AV=2, GRR=3
    grr_bg  = (
        colors.HexColor("#FADBD8") if res.pct_grr > 30
        else colors.HexColor("#FDEBD0") if res.pct_grr > 10
        else colors.HexColor("#D5F5E3")
    )
    vc_tbl = Table(vc_rows, colWidths=[2.55 * inch, 1.35 * inch, 1.0 * inch, 1.6 * inch])
    vc_tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0),        (-1, 0),        _C_DARK),
        ("TEXTCOLOR",      (0, 0),        (-1, 0),        _C_WHITE),
        ("FONTNAME",       (0, 0),        (-1, 0),        "Helvetica-Bold"),
        ("FONTNAME",       (0, GRR_ROW),  (-1, GRR_ROW),  "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1),        (-1, -1),        [_C_LGRAY, _C_WHITE]),
        ("BACKGROUND",     (0, GRR_ROW),  (-1, GRR_ROW),  grr_bg),
        ("GRID",           (0, 0),        (-1, -1),        0.4, _C_BORD),
        ("FONTSIZE",       (0, 0),        (-1, -1),        8.5),
        ("ALIGN",          (1, 0),        (-1, -1),        "CENTER"),
        ("ALIGN",          (0, 0),        (0, -1),         "LEFT"),
        ("TOPPADDING",     (0, 0),        (-1, -1),        5),
        ("BOTTOMPADDING",  (0, 0),        (-1, -1),        5),
        ("LEFTPADDING",    (0, 0),        (-1, -1),        7),
    ]))
    story += [vc_tbl, Spacer(1, 0.03 * inch)]
    story.append(Paragraph(
        "Assessment column: GR&R row uses AIAG pass/fail criteria "
        "(<=10% Acceptable / 10-30% Marginal / >30% Unacceptable). "
        "EV and AV rows show diagnostic level (Low / Moderate / High) "
        "to identify the dominant variation source.",
        s_note,
    ))

    # NDC note
    ndc_msg = (
        f"Number of Distinct Categories (NDC): <b>{res.ndc}</b> -- "
        + ("Adequate: gauge resolves >=5 distinct categories of part variation. [PASS]"
           if res.ndc >= NDC_MINIMUM
           else "Inadequate: NDC should be >=5. Gage improvement required. [FAIL]")
    )
    story.append(Paragraph(ndc_msg, s_body))

    if res.av_clamped:
        story.append(Paragraph(
            "Note: AV^2 computed as negative -- AV set to zero. "
            "Operator variation is not distinguishable from gauge repeatability noise.",
            s_note,
        ))

    if res.out_of_control:
        story.append(Paragraph(
            f"Warning: {len(res.out_of_control)} range(s) exceeded "
            f"UCL_R = {res.ucl_r:.5f}. Investigate these observations before "
            "accepting the study.",
            s_warn,
        ))

    story.append(Spacer(1, 0.10 * inch))

    # ---- Intermediate values (audit trail) --------------------------------
    story.append(Paragraph("Intermediate Calculation Values", s_section))
    iv_rows = [
        ["Parameter",               "Symbol",    "Value",                  "Formula"],
        ["Grand Mean",              "X-bar-bar", f"{res.grand_mean:.5f}",  "Mean of all measurements"],
        ["Avg Range (overall)",     "R-bar-bar", f"{res.r_bar_bar:.5f}",   "Mean of per-operator R-bars"],
        ["Upper Control Limit (R)", "UCL_R",     f"{res.ucl_r:.5f}",      f"D4({res.d4}) x R-bar-bar"],
        ["Operator Mean Spread",    "X-diff",    f"{res.x_diff:.5f}",     "max(op X-bar) - min(op X-bar)"],
        ["Part Range",              "Rp",        f"{res.rp:.5f}",         "max(part avg) - min(part avg)"],
        ["K1 constant (EV)",        "K1",        f"{res.k1}",             f"5.15 / d2*({res.n_trials} trials)"],
        ["K2 constant (AV)",        "K2",        f"{res.k2}",             f"5.15 / d2*({res.n_operators} operators)"],
        ["K3 constant (PV)",        "K3",        f"{res.k3}",             f"5.15 / d2*({res.n_parts} parts)"],
    ]
    iv_tbl = Table(iv_rows,
                   colWidths=[1.9 * inch, 1.0 * inch, 1.0 * inch, 2.6 * inch],
                   repeatRows=1)
    iv_tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), _C_MID),
        ("TEXTCOLOR",      (0, 0), (-1, 0), _C_WHITE),
        ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_C_WHITE, _C_LGRAY]),
        ("GRID",           (0, 0), (-1, -1), 0.4, _C_BORD),
        ("ALIGN",          (2, 0), (2, -1), "RIGHT"),
        ("TOPPADDING",     (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ("LEFTPADDING",    (0, 0), (-1, -1), 7),
    ]))
    story += [iv_tbl, Spacer(1, 0.12 * inch)]

    # ---- Per-operator breakdown -------------------------------------------
    story.append(Paragraph("Per-Operator Breakdown", s_section))
    op_header = ["Operator", "Grand Mean (X-bar)", "Avg Range (R-bar)"]
    op_rows   = [[op.name, f"{op.x_bar:.5f}", f"{op.r_bar:.5f}"]
                 for op in res.operator_stats]
    op_tbl    = Table([op_header] + op_rows,
                      colWidths=[2.0 * inch, 2.5 * inch, 2.0 * inch],
                      repeatRows=1)
    op_tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), _C_MID),
        ("TEXTCOLOR",      (0, 0), (-1, 0), _C_WHITE),
        ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_C_WHITE, _C_LGRAY]),
        ("GRID",           (0, 0), (-1, -1), 0.4, _C_BORD),
        ("ALIGN",          (1, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",     (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
        ("LEFTPADDING",    (0, 0), (-1, -1), 8),
    ]))
    story += [op_tbl, Spacer(1, 0.14 * inch)]

    # ---- Acceptance determination banner ---------------------------------
    story.append(Paragraph("Acceptance Determination", s_section))
    tol_note = (f"  |  %Tol(GRR) = {res.pct_tol_grr:.1f}%"
                if res.tolerance else "")
    icon = {"ACCEPTABLE": "PASS", "MARGINAL": "CAUTION",
            "UNACCEPTABLE": "FAIL"}.get(res.status, "")
    verdict_tbl = Table(
        [[Paragraph(
            f"[{icon}]  {res.status}   "
            f"(%GRR = {res.pct_grr:.1f}%  |  NDC = {res.ndc}{tol_note})",
            s_verdict,
        )]],
        colWidths=[7.0 * inch],
    )
    verdict_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor(res.verdict_color_hex)),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
    ]))
    story += [verdict_tbl, Spacer(1, 0.10 * inch)]

    # ---- AIAG criteria reference table ------------------------------------
    story.append(Paragraph("AIAG MSA Acceptance Criteria Reference", s_section))
    crit_rows = [
        ["%GRR",      "Assessment",    "Recommended Action"],
        ["<= 10%",    "ACCEPTABLE",    "Gauge approved. Measurement system is capable of product acceptance decisions."],
        ["10% - 30%", "MARGINAL",      "May be acceptable depending on importance, cost, and customer concurrence. "
                                       "Investigate dominant variation source (EV vs. AV)."],
        ["> 30%",     "UNACCEPTABLE",  "Do not use for product acceptance. Identify root cause and correct before "
                                       "re-study. Check gage discrimination, components, technique, environment."],
    ]
    crit_tbl = Table(crit_rows, colWidths=[0.85 * inch, 1.20 * inch, 4.45 * inch])
    crit_tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), colors.HexColor("#566573")),
        ("TEXTCOLOR",      (0, 0), (-1, 0), _C_WHITE),
        ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1), 7.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.HexColor("#D5F5E3"),
          colors.HexColor("#FDEBD0"),
          colors.HexColor("#FADBD8")]),
        ("GRID",           (0, 0), (-1, -1), 0.4, _C_BORD),
        ("TOPPADDING",     (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ("LEFTPADDING",    (0, 0), (-1, -1), 6),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story += [crit_tbl, Spacer(1, 0.14 * inch)]

    # ---- Charts -----------------------------------------------------------
    story.append(hr_light)
    story.append(Spacer(1, 0.08 * inch))
    story.append(Paragraph("Control Charts", s_section))
    story += [
        _chart_components(res),
        Spacer(1, 0.08 * inch),
        _chart_range(res),
        Spacer(1, 0.08 * inch),
        _chart_xbar(res),
        Spacer(1, 0.10 * inch),
        hr_light,
    ]

    # ---- Interpretation notes --------------------------------------------
    interp_map = {
        "ACCEPTABLE": (
            "The measurement system is ACCEPTABLE per AIAG MSA 4th Edition criteria. "
            "%GR&R <= 10%: the gage contributes minimal variation relative to total process "
            "variation. This instrument may be used for product acceptance decisions. "
            "Continue routine calibration per your control plan."
        ),
        "MARGINAL": (
            "The measurement system is MARGINAL (10% < %GR&R <= 30%). "
            "Use with caution -- approval should consider application importance, "
            "cost of gage improvement, and customer concurrence. Compare EV vs. AV "
            "to identify the dominant source: if AV > EV, focus on operator training "
            "and fixture standardization; if EV > AV, evaluate gage resolution or "
            "replacement."
        ),
        "UNACCEPTABLE": (
            "The measurement system is UNACCEPTABLE (%GR&R > 30%). Do not use "
            "this gage for product acceptance or process control. Identify and correct "
            "root cause before re-study. Common causes: insufficient gage discrimination, "
            "worn components, inconsistent measurement technique, or environmental factors."
        ),
    }
    story.append(Paragraph(interp_map.get(res.status, ""), s_note))
    story.append(Spacer(1, 0.14 * inch))

    # ---- Footer ----------------------------------------------------------
    story.append(HRFlowable(width="100%", thickness=0.5, color=_C_BORD))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Generated by grr_tool.py -- AIAG MSA 4th Edition Average &amp; Range Method. "
        "Study variation expressed as 5.15-sigma (99% coverage). "
        "%Study Variation = 100 x (component / TV). "
        "Regulatory basis: 21 CFR Part 820.72 (FDA QSR). "
        "This report is a controlled quality record -- retain per document control procedures.",
        s_footer,
    ))

    doc.build(story)
    print(f"[+] PDF report written to: {output_path}")


# ---------------------------------------------------------------------------
# Interactive HTML Dashboard
# ---------------------------------------------------------------------------

def build_dashboard(
    res:            GRRResults,
    output_path:    Path,
    equipment:      str,
    study_operator: str,
    title:          str = "GR&R Analysis Dashboard",
) -> None:
    """
    Generate a self-contained interactive HTML dashboard using Chart.js.

    The dashboard includes:
      - %GRR gauge meter with color zones (green/amber/red)
      - Variance components bar chart with AIAG threshold lines
      - R-Chart (range by part and operator) with UCL_R line
      - X-bar Chart (mean by part and operator)
      - Operator toggle buttons to show/hide individual operators
      - Summary metrics table and per-operator breakdown table
      - %Tolerance section (when tolerance was provided)

    All data is pre-computed by Python and embedded as JSON in the HTML --
    no server required. Open the file directly in any modern browser.
    """
    ops       = [op.name for op in res.operator_stats]
    parts     = res.parts
    ranges_2d = [op.part_ranges for op in res.operator_stats]
    means_2d  = [op.part_means  for op in res.operator_stats]
    r_bars    = [op.r_bar for op in res.operator_stats]
    x_bars    = [op.x_bar for op in res.operator_stats]

    js_data = {
        "title":         title,
        "equipment":     equipment,
        "studyOperator": study_operator,
        "reportDate":    str(date.today()),
        "parts":         parts,
        "ops":           ops,
        "ranges":        ranges_2d,
        "means":         means_2d,
        "rBars":         r_bars,
        "xBars":         x_bars,
        "rBarBar":       res.r_bar_bar,
        "uclR":          res.ucl_r,
        "grandMean":     res.grand_mean,
        "rp":            res.rp,
        "xDiff":         res.x_diff,
        "ev":  res.ev,  "pctEV":  res.pct_ev,
        "av":  res.av,  "pctAV":  res.pct_av,
        "grr": res.grr, "pctGRR": res.pct_grr,
        "pv":  res.pv,  "pctPV":  res.pct_pv,
        "tv":  res.tv,
        "ndc":          res.ndc,
        "status":       res.status,
        "avClamped":    res.av_clamped,
        "outOfControl": len(res.out_of_control),
        "k1": res.k1, "k2": res.k2, "k3": res.k3, "d4": res.d4,
        "nParts": res.n_parts, "nOps": res.n_operators, "nTrials": res.n_trials,
        "tolerance":  res.tolerance,
        "pctTolEV":   res.pct_tol_ev,
        "pctTolAV":   res.pct_tol_av,
        "pctTolGRR":  res.pct_tol_grr,
    }

    sc_map = {
        "ACCEPTABLE":   {"bg": "#1a5c2e", "badge": "#27AE60", "text": "#d4f1e0"},
        "MARGINAL":     {"bg": "#7a3a00", "badge": "#E67E22", "text": "#fde9d0"},
        "UNACCEPTABLE": {"bg": "#5c1a1a", "badge": "#C0392B", "text": "#f9d6d6"},
    }
    sc = sc_map.get(res.status, sc_map["UNACCEPTABLE"])
    op_palette = ["#1A3A5C", "#E67E22", "#16A085", "#8E44AD", "#C0392B"]
    gauge_left = f"{min(res.pct_grr, 100):.2f}%"

    pct_grr_color = (
        "var(--green)" if res.pct_grr <= 10
        else "var(--orange)" if res.pct_grr <= 30
        else "var(--red)"
    )
    ndc_color = "var(--green)" if res.ndc >= 5 else "var(--red)"
    ndc_label = "Adequate (&ge;5 required)" if res.ndc >= 5 else "Inadequate (&lt;5)"

    tol_section = ""
    if res.tolerance:
        tol_section = f"""
      <div class="kpi">
        <div class="kpi-label">%Tolerance EV</div>
        <div class="kpi-value">{res.pct_tol_ev:.1f}%</div>
        <div class="kpi-sub">Tol = {res.tolerance}</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">%Tolerance AV</div>
        <div class="kpi-value">{res.pct_tol_av:.1f}%</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">%Tolerance GRR</div>
        <div class="kpi-value">{res.pct_tol_grr:.1f}%</div>
      </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --navy:   #1A3A5C;  --teal:  #16A085;
    --orange: #E67E22;  --green: #27AE60;
    --red:    #C0392B;  --grey:  #95A5A6;
    --bg:     #f0f3f7;  --card:  #ffffff;
    --border: #d0d7e2;  --text:  #1a2332;  --muted: #667388;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           background: var(--bg); color: var(--text); font-size: 14px; }}
  header {{ background: var(--navy); color: #fff; padding: 18px 32px 14px;
             display: flex; justify-content: space-between; align-items: center;
             flex-wrap: wrap; gap: 8px; }}
  header h1 {{ font-size: 1.25rem; font-weight: 700; letter-spacing: .02em; }}
  header .meta {{ font-size: 0.78rem; opacity: .75; text-align: right; line-height: 1.6; }}
  .verdict-bar {{ background: {sc['bg']}; color: {sc['text']};
                   padding: 12px 32px; display: flex; align-items: center;
                   gap: 16px; flex-wrap: wrap; }}
  .verdict-badge {{ background: {sc['badge']}; color: #fff; font-size: 0.85rem;
                     font-weight: 700; padding: 4px 14px; border-radius: 4px;
                     letter-spacing: .05em; }}
  .verdict-detail {{ font-size: 0.9rem; opacity: .9; }}
  main {{ max-width: 1200px; margin: 24px auto; padding: 0 20px; }}
  .grid {{ display: grid; gap: 20px; }}
  .grid-2 {{ grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); }}
  .grid-3 {{ grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px;
            padding: 20px 22px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
  .card h2 {{ font-size: 0.9rem; font-weight: 700; color: var(--navy);
               text-transform: uppercase; letter-spacing: .06em; margin-bottom: 14px; }}
  .chart-wrap {{ position: relative; height: 260px; }}
  .chart-wrap-tall {{ position: relative; height: 300px; }}
  .kpi-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
  .kpi {{ background: #f7f9fc; border: 1px solid var(--border); border-radius: 6px;
           padding: 10px 14px; }}
  .kpi-label {{ font-size: 0.72rem; color: var(--muted); text-transform: uppercase;
                 letter-spacing: .05em; }}
  .kpi-value {{ font-size: 1.35rem; font-weight: 700; color: var(--navy); margin-top: 2px; }}
  .kpi-sub {{ font-size: 0.72rem; color: var(--muted); margin-top: 1px; }}
  .gauge-wrap {{ display: flex; flex-direction: column; align-items: center; gap: 10px;
                  padding: 10px 0 4px; }}
  .gauge-track {{ width: 100%; height: 18px; border-radius: 9px; overflow: hidden;
                   display: flex; position: relative; }}
  .gz-accept {{ background: var(--green); flex: 10; }}
  .gz-marg   {{ background: var(--orange); flex: 20; }}
  .gz-bad    {{ background: var(--red);    flex: 70; }}
  .gauge-pin-row {{ width: 100%; position: relative; height: 24px; }}
  .gauge-pin {{ position: absolute; transform: translateX(-50%); display: flex;
                 flex-direction: column; align-items: center; font-size: 0.8rem;
                 font-weight: 700; color: var(--navy); }}
  .gauge-pin::before {{ content: ""; width: 2px; height: 12px; background: var(--navy);
                         display: block; margin-bottom: 2px; }}
  .gauge-labels {{ width: 100%; display: flex; justify-content: space-between;
                    font-size: 0.7rem; color: var(--muted); }}
  .toggle-row {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .op-btn {{ padding: 4px 14px; border-radius: 4px; border: 2px solid;
              font-size: 0.78rem; font-weight: 600; cursor: pointer;
              transition: opacity .15s; background: #fff; }}
  .op-btn.off {{ opacity: .35; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
  th {{ background: var(--navy); color: #fff; padding: 7px 10px;
        text-align: left; font-weight: 600; font-size: 0.75rem; }}
  td {{ padding: 6px 10px; border-bottom: 1px solid var(--border); }}
  tr:nth-child(even) td {{ background: #f7f9fc; }}
  tr.grr-row td {{ font-weight: 700; }}
  .tag {{ display: inline-block; padding: 1px 8px; border-radius: 3px;
           font-size: 0.72rem; font-weight: 700; }}
  .tag-ok   {{ background: #d5f5e3; color: #1a5c2e; }}
  .tag-mg   {{ background: #fdebd0; color: #7a3a00; }}
  .tag-bad  {{ background: #fadbd8; color: #5c1a1a; }}
  .tag-info {{ background: #e8f0fa; color: #1a3a5c; }}
  footer {{ text-align: center; font-size: 0.72rem; color: var(--muted);
             padding: 24px 16px; border-top: 1px solid var(--border); margin-top: 32px; }}
</style>
</head>
<body>

<header>
  <div>
    <h1>&#x1F4CF; {title}</h1>
    <div style="font-size:.78rem;opacity:.7;margin-top:3px">
      AIAG MSA 4th Edition &mdash; Average &amp; Range Method
    </div>
  </div>
  <div class="meta">
    <div><b>Equipment:</b> {equipment}</div>
    <div><b>Study by:</b> {study_operator}</div>
    <div><b>Date:</b> {date.today()}</div>
  </div>
</header>

<div class="verdict-bar">
  <span class="verdict-badge">{res.status}</span>
  <span class="verdict-detail">
    %GRR = <b>{res.pct_grr:.1f}%</b> &nbsp;|&nbsp;
    NDC = <b>{res.ndc}</b> &nbsp;|&nbsp;
    {res.n_parts} parts &times; {res.n_operators} operators &times; {res.n_trials} trials
    {"&nbsp;|&nbsp; %Tol(GRR) = <b>" + f"{res.pct_tol_grr:.1f}%" + "</b>" if res.tolerance else ""}
  </span>
</div>

<main>

<!-- Row 1: KPIs + Gauge -->
<div class="grid grid-2" style="margin-bottom:20px">
  <div class="card">
    <h2>Key Metrics</h2>
    <div class="kpi-grid">
      <div class="kpi">
        <div class="kpi-label">Gauge R&amp;R (%GRR)</div>
        <div class="kpi-value" style="color:{pct_grr_color}">{res.pct_grr:.1f}%</div>
        <div class="kpi-sub">AIAG: &le;10% accept / &le;30% marginal</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">NDC</div>
        <div class="kpi-value" style="color:{ndc_color}">{res.ndc}</div>
        <div class="kpi-sub">{ndc_label}</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Repeatability (EV)</div>
        <div class="kpi-value">{res.pct_ev:.1f}%</div>
        <div class="kpi-sub">&sigma; = {res.ev:.5f}</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Reproducibility (AV)</div>
        <div class="kpi-value">{res.pct_av:.1f}%</div>
        <div class="kpi-sub">&sigma; = {res.av:.5f}{"  (clamped)" if res.av_clamped else ""}</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Part Variation (PV)</div>
        <div class="kpi-value">{res.pct_pv:.1f}%</div>
        <div class="kpi-sub">&sigma; = {res.pv:.5f}</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Total Variation (TV)</div>
        <div class="kpi-value">{res.tv:.5f}</div>
        <div class="kpi-sub">R-bar = {res.r_bar_bar:.5f}</div>
      </div>
      {tol_section}
    </div>
  </div>

  <div class="card">
    <h2>%GRR Acceptance Gauge</h2>
    <div class="gauge-wrap">
      <div class="gauge-track">
        <div class="gz-accept"></div>
        <div class="gz-marg"></div>
        <div class="gz-bad"></div>
      </div>
      <div class="gauge-pin-row">
        <div class="gauge-pin" style="left:{gauge_left}">{res.pct_grr:.1f}%</div>
      </div>
      <div class="gauge-labels">
        <span>0%</span><span>10%</span><span>30%</span><span>100%</span>
      </div>
    </div>
    <div style="margin-top:16px">
      <table>
        <thead><tr><th>Zone</th><th>Range</th><th>AIAG Verdict</th></tr></thead>
        <tbody>
          <tr><td style="color:var(--green);font-weight:700">Acceptable</td>
              <td>&le; 10%</td><td><span class="tag tag-ok">PASS</span></td></tr>
          <tr><td style="color:var(--orange);font-weight:700">Marginal</td>
              <td>10% &ndash; 30%</td><td><span class="tag tag-mg">CAUTION</span></td></tr>
          <tr><td style="color:var(--red);font-weight:700">Unacceptable</td>
              <td>&gt; 30%</td><td><span class="tag tag-bad">FAIL</span></td></tr>
        </tbody>
      </table>
    </div>
  </div>
</div>

<!-- Operator toggles -->
<div class="card" style="margin-bottom:20px">
  <h2>Operator Filter</h2>
  <div class="toggle-row" id="op-toggles"></div>
</div>

<!-- Charts row -->
<div class="grid grid-2" style="margin-bottom:20px">
  <div class="card">
    <h2>Variance Components (%Study Variation)</h2>
    <div class="chart-wrap"><canvas id="comp-chart"></canvas></div>
  </div>
  <div class="card">
    <h2>R-Chart (Range by Part)</h2>
    <div class="chart-wrap"><canvas id="r-chart"></canvas></div>
  </div>
</div>

<!-- X-bar chart full width -->
<div class="card" style="margin-bottom:20px">
  <h2>X-bar Chart (Mean by Part and Operator)</h2>
  <div class="chart-wrap-tall"><canvas id="xbar-chart"></canvas></div>
</div>

<!-- Metrics table -->
<div class="card" style="margin-bottom:20px">
  <h2>Detailed Variance Components</h2>
  <table>
    <thead>
      <tr><th>Component</th><th>Study Variation (&sigma;)</th>
          <th>% of TV</th><th>Assessment</th></tr>
    </thead>
    <tbody id="metrics-body"></tbody>
  </table>
  <p style="font-size:.72rem;color:var(--muted);margin-top:8px">
    GR&amp;R row: AIAG pass/fail criteria (<=10%/10-30%/>30%).
    EV and AV: diagnostic level (Low/Moderate/High) identifying dominant variation source.
  </p>
</div>

<!-- Operator breakdown -->
<div class="card" style="margin-bottom:20px">
  <h2>Per-Operator Breakdown</h2>
  <table>
    <thead><tr><th>Operator</th><th>Grand Mean (X-bar)</th><th>Avg Range (R-bar)</th></tr></thead>
    <tbody id="op-body"></tbody>
  </table>
</div>

</main>

<footer>
  Generated by grr_tool.py &mdash; AIAG MSA 4th Edition Average &amp; Range Method &bull;
  5.15&sigma; study variation convention &bull; Regulatory basis: 21 CFR 820.72 (FDA QSR)
</footer>

<script>
const D = {json.dumps(js_data, indent=2)};
const OP_COLORS = {json.dumps(op_palette)};
const activeOps = new Set(D.ops);
const charts = {{}};

// Operator toggle buttons
function buildToggles() {{
  const row = document.getElementById('op-toggles');
  D.ops.forEach((op, i) => {{
    const btn = document.createElement('button');
    btn.className = 'op-btn';
    btn.id = 'btn-' + op;
    btn.textContent = 'Operator ' + op;
    btn.style.borderColor = OP_COLORS[i % OP_COLORS.length];
    btn.style.color = OP_COLORS[i % OP_COLORS.length];
    btn.addEventListener('click', () => {{
      if (activeOps.has(op)) activeOps.delete(op); else activeOps.add(op);
      btn.classList.toggle('off', !activeOps.has(op));
      ['r-chart', 'xbar-chart'].forEach(id => {{
        const ch = charts[id];
        if (!ch) return;
        D.ops.forEach((o, j) => ch.setDatasetVisibility(j, activeOps.has(o)));
        ch.update();
      }});
      renderMetrics();
    }});
    row.appendChild(btn);
  }});
}}

// AIAG threshold line plugin (components chart only)
const thresholdPlugin = {{
  id: 'thresholds',
  afterDraw(chart) {{
    const {{ctx, chartArea: {{left, right}}, scales: {{y}}}} = chart;
    [[10,'#27AE60','10% (Acceptable)'], [30,'#C0392B','30% (Unacceptable)']].forEach(([v,c,lbl]) => {{
      const yp = y.getPixelForValue(v);
      ctx.save();
      ctx.setLineDash([5,4]); ctx.strokeStyle = c; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(left,yp); ctx.lineTo(right,yp); ctx.stroke();
      ctx.setLineDash([]); ctx.fillStyle = c; ctx.font='600 10px sans-serif';
      ctx.textAlign='right'; ctx.fillText(lbl, right-4, yp-4);
      ctx.restore();
    }});
  }}
}};
Chart.register(thresholdPlugin);

// Components bar chart
function buildComp() {{
  const vals = [D.pctEV, D.pctAV, D.pctGRR, D.pctPV];
  const bg = ['#16A085','#E67E22',
    D.pctGRR>30?'#C0392B':D.pctGRR>10?'#E67E22':'#27AE60', '#1A3A5C'];
  charts['comp-chart'] = new Chart(document.getElementById('comp-chart'), {{
    type: 'bar',
    data: {{
      labels: ['Repeatability (EV)','Reproducibility (AV)','Gauge R&R','Part Variation (PV)'],
      datasets: [{{ data: vals, backgroundColor: bg, borderRadius: 4 }}]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      plugins: {{ legend:{{display:false}},
        tooltip:{{ callbacks:{{ label: c => ' '+c.parsed.y.toFixed(1)+'%' }} }} }},
      scales: {{
        y: {{ suggestedMax: Math.ceil(Math.max(...vals,32)/10)*10+10,
               ticks:{{ callback: v => v+'%' }}, grid:{{ color:'#e8ecf0' }} }},
        x: {{ grid:{{ display:false }} }}
      }}
    }}
  }});
}}

// R-Chart
function buildRChart() {{
  const datasets = D.ops.map((op,i) => ({{
    label:'Op. '+op, data: D.ranges[i],
    borderColor: OP_COLORS[i%OP_COLORS.length],
    backgroundColor: OP_COLORS[i%OP_COLORS.length]+'22',
    pointRadius:5, borderWidth:1.5, tension:0.1,
  }}));
  datasets.push({{ label:'UCL_R = '+D.uclR.toFixed(4),
    data: Array(D.parts.length).fill(D.uclR),
    borderColor:'#C0392B', borderDash:[6,4], borderWidth:1.5, pointRadius:0, fill:false }});
  datasets.push({{ label:'R-bar = '+D.rBarBar.toFixed(4),
    data: Array(D.parts.length).fill(D.rBarBar),
    borderColor:'#95A5A6', borderDash:[3,3], borderWidth:1.2, pointRadius:0, fill:false }});
  charts['r-chart'] = new Chart(document.getElementById('r-chart'), {{
    type:'line', data:{{ labels:D.parts, datasets }},
    options:{{ responsive:true, maintainAspectRatio:false,
      plugins:{{ legend:{{ position:'bottom', labels:{{ boxWidth:12, font:{{ size:11 }} }} }} }},
      scales:{{ y:{{ grid:{{ color:'#e8ecf0' }} }}, x:{{ grid:{{ display:false }} }} }}
    }}
  }});
}}

// X-bar Chart
function buildXbar() {{
  const datasets = D.ops.map((op,i) => ({{
    label:'Op. '+op, data: D.means[i],
    borderColor: OP_COLORS[i%OP_COLORS.length],
    backgroundColor: OP_COLORS[i%OP_COLORS.length]+'22',
    pointRadius:5, borderWidth:1.5, tension:0.1,
  }}));
  charts['xbar-chart'] = new Chart(document.getElementById('xbar-chart'), {{
    type:'line', data:{{ labels:D.parts, datasets }},
    options:{{ responsive:true, maintainAspectRatio:false,
      plugins:{{ legend:{{ position:'bottom', labels:{{ boxWidth:12, font:{{ size:11 }} }} }} }},
      scales:{{ y:{{ grid:{{ color:'#e8ecf0' }} }}, x:{{ grid:{{ display:false }} }} }}
    }}
  }});
}}

// Metrics table
function renderMetrics() {{
  function verdict(p) {{ return p<=10?'Acceptable':p<=30?'Marginal':'Unacceptable'; }}
  function level(p)   {{ return p<=10?'Low':p<=30?'Moderate':'High'; }}
  function tag(s) {{
    const cls = {{Acceptable:'tag-ok',Low:'tag-ok',Marginal:'tag-mg',Moderate:'tag-mg',
                  Unacceptable:'tag-bad',High:'tag-bad','&mdash;':'tag-info'}}[s]||'tag-info';
    return `<span class="tag ${{cls}}">${{s}}</span>`;
  }}
  const rows = [
    ['EV &mdash; Equipment (Repeatability)',   D.ev,  D.pctEV,  level(D.pctEV)],
    ['AV &mdash; Appraiser (Reproducibility)', D.av,  D.pctAV,  level(D.pctAV)],
    ['GR&amp;R &mdash; Combined',              D.grr, D.pctGRR, verdict(D.pctGRR)],
    ['PV &mdash; Part Variation',              D.pv,  D.pctPV,  '&mdash;'],
    ['TV &mdash; Total Variation',             D.tv,  100.0,    '&mdash;'],
  ];
  let html = rows.map((r,i) =>
    `<tr class="${{i===2?'grr-row':''}}">
       <td>${{r[0]}}</td><td>${{r[1].toFixed(5)}}</td>
       <td>${{r[2].toFixed(1)}}%</td><td>${{tag(r[3])}}</td></tr>`
  ).join('');
  if (D.tolerance) {{
    html += '<tr><td colspan="4" style="height:6px;background:#f7f9fc"></td></tr>';
    [['%Tolerance (EV)',D.pctTolEV],['%Tolerance (AV)',D.pctTolAV],
     ['%Tolerance (GRR)',D.pctTolGRR]].forEach(([l,v]) => {{
      html += `<tr><td>${{l}}</td><td>&mdash;</td><td>${{v.toFixed(1)}}%</td><td>${{tag(verdict(v))}}</td></tr>`;
    }});
  }}
  document.getElementById('metrics-body').innerHTML = html;
}}

// Operator breakdown table
function renderOpTable() {{
  document.getElementById('op-body').innerHTML = D.ops.map((op,i) =>
    `<tr>
       <td style="color:${{OP_COLORS[i%OP_COLORS.length]}};font-weight:700">${{op}}</td>
       <td>${{D.xBars[i].toFixed(5)}}</td>
       <td>${{D.rBars[i].toFixed(5)}}</td></tr>`
  ).join('');
}}

// Init
buildToggles(); buildComp(); buildRChart(); buildXbar();
renderMetrics(); renderOpTable();
</script>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")
    print(f"[+] Dashboard written to: {output_path}")


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="grr_tool.py",
        description=(
            "Gauge R&R Analysis Tool -- AIAG MSA 4th Edition\n"
            "Analyzes measurement system variation for medical device quality engineering.\n"
            "Outputs: console summary, PDF report (with charts), and/or interactive HTML dashboard."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Generate sample data, PDF + dashboard:\n"
            "  python grr_tool.py --generate-sample --input sample.csv \\\n"
            "      --output report.pdf --dashboard dashboard.html \\\n"
            "      --equipment 'Mitutoyo 293-340-30' --operator 'J. Martinez'\n\n"
            "  # Existing CSV, PDF only, with tolerance:\n"
            "  python grr_tool.py --input data.csv --output report.pdf \\\n"
            "      --tolerance 0.050 --equipment 'Caliper SN-0042'\n\n"
            "  # Dashboard only:\n"
            "  python grr_tool.py --input data.csv --dashboard results.html\n"
        ),
    )
    p.add_argument("--input", "-i",   type=Path, required=True, metavar="CSV_FILE",
                   help="Input CSV (columns: Part, Operator, Trial1, Trial2[, Trial3, ...])")
    p.add_argument("--output", "-o",  type=Path, default=None,  metavar="PDF_FILE",
                   help="Output PDF path (default: <input_stem>_grr_report.pdf when no --dashboard)")
    p.add_argument("--dashboard", "-d", type=Path, default=None, metavar="HTML_FILE",
                   help="Output interactive HTML dashboard (e.g. grr_dashboard.html)")
    p.add_argument("--tolerance", "-t", type=float, default=None, metavar="TOLERANCE",
                   help="Full engineering tolerance range (e.g. 0.050 for +/-0.025 spec)")
    p.add_argument("--title",     type=str, default="GR&R Study Report", metavar="TITLE",
                   help='Report title (default: "GR&R Study Report")')
    p.add_argument("--equipment", "-e", type=str, default="Unspecified Gage", metavar="NAME",
                   help="Equipment / gage identifier (e.g. 'Mitutoyo 293-340-30 SN-1234')")
    p.add_argument("--operator",  type=str, default="Quality Engineering", metavar="NAME",
                   help="Name of QE or team who performed the study")
    p.add_argument("--generate-sample", action="store_true",
                   help="Generate a sample 10-part x 3-operator x 3-trial CSV before analysis")
    p.add_argument("--version", "-v", action="version",
                   version=f"%(prog)s {__version__}")
    return p.parse_args()


def main() -> None:
    """Main entry point -- orchestrates sample generation, analysis, and reporting."""
    args = parse_args()

    if args.generate_sample:
        generate_sample_data(args.input)

    # Default to PDF output when neither --output nor --dashboard is given
    pdf_path = args.output or (
        args.input.with_name(args.input.stem + "_grr_report.pdf")
        if not args.dashboard else None
    )

    records, n_parts, n_operators, n_trials = load_data(args.input)
    res = compute_grr(records, n_parts, n_operators, n_trials,
                      tolerance=args.tolerance)

    print_console_report(res, args.equipment, args.operator)

    if pdf_path:
        build_pdf_report(res, pdf_path, args.equipment, args.operator, args.title)

    if args.dashboard:
        build_dashboard(res, args.dashboard, args.equipment, args.operator, args.title)


if __name__ == "__main__":
    main()
