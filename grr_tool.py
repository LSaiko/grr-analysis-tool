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

__version__ = "2.0.0"

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

try:
    import scipy.stats as _scipy_stats
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False

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

# Hardcoded chi-squared percentile table for CI fallback when scipy is absent.
# Keys: degrees of freedom 1–30. Values: (chi2_0.025, chi2_0.975) for 95% CI
#       and (chi2_0.05, chi2_0.95) for 90% CI stored as (lo_95, hi_95, lo_90, hi_90).
_CHI2_TABLE: Dict[int, Tuple[float, float, float, float]] = {
    1:  (0.001, 5.024, 0.004, 3.841),
    2:  (0.051, 7.378, 0.103, 5.991),
    3:  (0.216, 9.348, 0.352, 7.815),
    4:  (0.484, 11.143, 0.711, 9.488),
    5:  (0.831, 12.833, 1.145, 11.070),
    6:  (1.237, 14.449, 1.635, 12.592),
    7:  (1.690, 16.013, 2.167, 14.067),
    8:  (2.180, 17.535, 2.733, 15.507),
    9:  (2.700, 19.023, 3.325, 16.919),
    10: (3.247, 20.483, 3.940, 18.307),
    11: (3.816, 21.920, 4.575, 19.675),
    12: (4.404, 23.337, 5.226, 21.026),
    13: (5.009, 24.736, 5.892, 22.362),
    14: (5.629, 26.119, 6.571, 23.685),
    15: (6.262, 27.488, 7.261, 24.996),
    16: (6.908, 28.845, 7.962, 26.296),
    17: (7.564, 30.191, 8.672, 27.587),
    18: (8.231, 31.526, 9.390, 28.869),
    19: (8.907, 32.852, 10.117, 30.144),
    20: (9.591, 34.170, 10.851, 31.410),
    21: (10.283, 35.479, 11.591, 32.671),
    22: (10.982, 36.781, 12.338, 33.924),
    23: (11.689, 38.076, 13.091, 35.172),
    24: (12.401, 39.364, 13.848, 36.415),
    25: (13.120, 40.646, 14.611, 37.652),
    26: (13.844, 41.923, 15.379, 38.885),
    27: (14.573, 43.194, 16.151, 40.113),
    28: (15.308, 44.461, 16.928, 41.337),
    29: (16.047, 45.722, 17.708, 42.557),
    30: (16.791, 46.979, 18.493, 43.773),
}


def _chi2_ppf(p: float, df: int) -> float:
    """Return chi-squared quantile at probability p for given df."""
    if _SCIPY_AVAILABLE:
        return float(_scipy_stats.chi2.ppf(p, df))
    df_clamped = max(1, min(30, df))
    lo95, hi95, lo90, hi90 = _CHI2_TABLE[df_clamped]
    if abs(p - 0.025) < 0.001: return lo95
    if abs(p - 0.975) < 0.001: return hi95
    if abs(p - 0.05)  < 0.001: return lo90
    if abs(p - 0.95)  < 0.001: return hi90
    return lo95


def _ci_on_sigma(sigma: float, df: int, confidence: float = 0.95) -> Tuple[float, float]:
    """Return (lower, upper) CI on a standard deviation estimate via chi-squared.
    sigma: estimated std dev; df: degrees of freedom for the estimate."""
    if df <= 0 or sigma <= 0:
        return (0.0, float("inf"))
    alpha = 1.0 - confidence
    chi_lo = _chi2_ppf(alpha / 2, df)
    chi_hi = _chi2_ppf(1 - alpha / 2, df)
    lower = sigma * math.sqrt(df / chi_hi) if chi_hi > 0 else 0.0
    upper = sigma * math.sqrt(df / chi_lo) if chi_lo > 0 else float("inf")
    return (lower, upper)

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
    usl:         Optional[float] = None   # upper spec limit (alternative to tolerance)
    lsl:         Optional[float] = None   # lower spec limit
    pct_tol_ev:  Optional[float] = None
    pct_tol_av:  Optional[float] = None
    pct_tol_grr: Optional[float] = None
    ndc_tol:     Optional[float] = None   # ndc computed from tolerance span

    # Quality indicator
    ndc:        int  = 0       # Number of Distinct Categories (floor integer)
    av_clamped: bool = False   # True when AV^2 < 0 and was clamped to 0
    status:     str  = ""      # ACCEPTABLE / MARGINAL / UNACCEPTABLE

    # Confidence intervals on variance components (95% and 90%)
    ev_ci95:  Tuple[float, float] = field(default_factory=lambda: (0.0, 0.0))
    av_ci95:  Tuple[float, float] = field(default_factory=lambda: (0.0, 0.0))
    grr_ci95: Tuple[float, float] = field(default_factory=lambda: (0.0, 0.0))
    ev_ci90:  Tuple[float, float] = field(default_factory=lambda: (0.0, 0.0))
    av_ci90:  Tuple[float, float] = field(default_factory=lambda: (0.0, 0.0))
    grr_ci90: Tuple[float, float] = field(default_factory=lambda: (0.0, 0.0))

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
    usl:         Optional[float] = None,
    lsl:         Optional[float] = None,
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
    # Resolve tolerance from usl/lsl if not directly provided
    if tolerance is None and usl is not None and lsl is not None:
        tolerance = usl - lsl

    res = GRRResults(
        n_parts=n_parts, n_operators=n_operators, n_trials=n_trials,
        tolerance=tolerance, usl=usl, lsl=lsl,
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
        # Secondary ndc based on tolerance span (AIAG formula variant)
        if res.grr > 0:
            res.ndc_tol = 1.41 * (tolerance / res.grr)

    # Confidence intervals (AIAG MSA 4th Ed. Appendix C chi-squared approach)
    # df_ev = n_operators * n_parts * (n_trials - 1)
    df_ev  = n_operators * n_parts * (n_trials - 1)
    df_pv  = n_parts - 1
    # EV sigma = ev / 5.15 (convert study variation back to sigma for CI calc)
    sigma_ev = res.ev / 5.15 if res.ev > 0 else 0.0
    res.ev_ci95 = tuple(v * 5.15 for v in _ci_on_sigma(sigma_ev, df_ev, 0.95))
    res.ev_ci90 = tuple(v * 5.15 for v in _ci_on_sigma(sigma_ev, df_ev, 0.90))
    # AV CI is approximate — use operator df
    sigma_av = res.av / 5.15 if res.av > 0 else 0.0
    df_av = max(1, n_operators - 1)
    res.av_ci95 = tuple(v * 5.15 for v in _ci_on_sigma(sigma_av, df_av, 0.95))
    res.av_ci90 = tuple(v * 5.15 for v in _ci_on_sigma(sigma_av, df_av, 0.90))
    # GR&R CI: propagate EV and AV CIs via conservative bound
    grr_lo95 = math.sqrt(max(0.0, res.ev_ci95[0]**2 + res.av_ci95[0]**2))
    grr_hi95 = math.sqrt(res.ev_ci95[1]**2 + res.av_ci95[1]**2)
    res.grr_ci95 = (grr_lo95, grr_hi95)
    grr_lo90 = math.sqrt(max(0.0, res.ev_ci90[0]**2 + res.av_ci90[0]**2))
    grr_hi90 = math.sqrt(res.ev_ci90[1]**2 + res.av_ci90[1]**2)
    res.grr_ci90 = (grr_lo90, grr_hi90)

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
# Linearity & Bias Study  (Task 4A)
# ---------------------------------------------------------------------------

@dataclass
class LinearityResults:
    reference_values: List[float]
    biases:           List[float]   # mean_measurement - reference for each level
    slope:            float = 0.0
    intercept:        float = 0.0
    r_squared:        float = 0.0
    slope_p_value:    Optional[float] = None
    linearity_pct:    Optional[float] = None   # |slope| * process_range / TV * 100
    process_range:    Optional[float] = None

@dataclass
class BiasResults:
    bias:          float = 0.0
    bias_pct:      float = 0.0   # % of tolerance
    t_statistic:   float = 0.0
    p_value:       Optional[float] = None
    ci_95_lower:   float = 0.0
    ci_95_upper:   float = 0.0
    n:             int   = 0
    std_dev:       float = 0.0


def compute_linearity(
    measurements:    List[float],
    reference_values: List[float],
    tolerance:       Optional[float] = None,
) -> LinearityResults:
    """Fit bias = a + b*reference regression and compute linearity metrics."""
    if len(measurements) != len(reference_values):
        sys.exit("[ERROR] --reference-values count must match measurement count.")

    refs  = np.array(reference_values, dtype=float)
    meas  = np.array(measurements, dtype=float)
    biases = meas - refs

    # Linear regression
    n     = len(refs)
    x_bar = refs.mean()
    y_bar = biases.mean()
    Sxx   = float(np.sum((refs - x_bar) ** 2))
    Sxy   = float(np.sum((refs - x_bar) * (biases - y_bar)))
    slope     = Sxy / Sxx if Sxx > 0 else 0.0
    intercept = y_bar - slope * x_bar
    y_hat     = slope * refs + intercept
    ss_res    = float(np.sum((biases - y_hat) ** 2))
    ss_tot    = float(np.sum((biases - y_bar) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    slope_p = None
    if _SCIPY_AVAILABLE and n > 2:
        _, _, _, p_value, _ = _scipy_stats.linregress(refs, biases)
        slope_p = float(p_value)

    proc_range = float(refs.max() - refs.min()) if len(refs) > 1 else None
    lin_pct    = None
    if tolerance and tolerance > 0 and proc_range is not None:
        lin_pct = abs(slope) * proc_range / tolerance * 100.0

    return LinearityResults(
        reference_values=reference_values,
        biases=biases.tolist(),
        slope=slope,
        intercept=intercept,
        r_squared=r_squared,
        slope_p_value=slope_p,
        linearity_pct=lin_pct,
        process_range=proc_range,
    )


def compute_bias(
    measurements: List[float],
    reference:    float,
    tolerance:    Optional[float] = None,
) -> BiasResults:
    """Compute bias statistics for a single known reference artifact."""
    arr   = np.array(measurements, dtype=float)
    n     = len(arr)
    bias  = float(arr.mean() - reference)
    std   = float(arr.std(ddof=1)) if n > 1 else 0.0
    se    = std / math.sqrt(n) if n > 0 else 0.0
    t_stat = bias / se if se > 0 else 0.0

    p_val = None
    if _SCIPY_AVAILABLE and n > 1:
        p_val = float(2.0 * _scipy_stats.t.sf(abs(t_stat), df=n - 1))

    # 95% CI using t-distribution
    if _SCIPY_AVAILABLE and n > 1:
        t_crit = float(_scipy_stats.t.ppf(0.975, df=n - 1))
    else:
        t_crit = 2.0  # conservative approximation
    ci_lo = bias - t_crit * se
    ci_hi = bias + t_crit * se

    bias_pct = 100.0 * abs(bias) / tolerance if tolerance and tolerance > 0 else 0.0

    return BiasResults(
        bias=bias, bias_pct=bias_pct,
        t_statistic=t_stat, p_value=p_val,
        ci_95_lower=ci_lo, ci_95_upper=ci_hi,
        n=n, std_dev=std,
    )


def _chart_linearity(lin: LinearityResults, tolerance: Optional[float]) -> Image:
    """Scatter of bias vs. reference with regression line and 95% CI bands."""
    refs   = np.array(lin.reference_values)
    biases = np.array(lin.biases)
    x_fit  = np.linspace(refs.min(), refs.max(), 100)
    y_fit  = lin.slope * x_fit + lin.intercept

    # Approximate 95% PI band
    n   = len(refs)
    se  = math.sqrt(sum((b - (lin.slope * r + lin.intercept))**2
                        for r, b in zip(lin.reference_values, lin.biases)) / max(n - 2, 1))
    se_arr = se * np.sqrt(1/n + (x_fit - refs.mean())**2 / max(np.sum((refs - refs.mean())**2), 1e-12))

    fig, ax = plt.subplots(figsize=(6.8, 3.5), facecolor="white")
    ax.scatter(refs, biases, color=NAVY, zorder=4, label="Observed bias", s=55)
    ax.plot(x_fit, y_fit, color=TEAL, linewidth=1.8, label=f"y = {lin.slope:.5f}x + {lin.intercept:.5f}")
    ax.fill_between(x_fit, y_fit - 2*se_arr, y_fit + 2*se_arr,
                    alpha=0.12, color=TEAL, label="95% CI band")
    ax.axhline(0, color=GREY, linestyle="--", linewidth=0.9)
    ax.set_xlabel("Reference value", fontsize=9)
    ax.set_ylabel("Bias (measured − reference)", fontsize=9)
    ax.set_title("Linearity Study — Bias vs. Reference Value", fontsize=10,
                 fontweight="bold", pad=8)
    ax.legend(fontsize=7.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return _fig_to_image(fig, 6.8, 3.5)


# ---------------------------------------------------------------------------
# Nested GR&R  (Task 4B — destructive testing)
# ---------------------------------------------------------------------------

@dataclass
class NestedGRRResults:
    ev:      float = 0.0   # repeatability
    av:      float = 0.0   # operator variation
    grr:     float = 0.0
    pv:      float = 0.0
    tv:      float = 0.0
    pct_ev:  float = 0.0
    pct_av:  float = 0.0
    pct_grr: float = 0.0
    pct_pv:  float = 0.0
    ndc:     int   = 0
    status:  str   = ""
    n_operators: int = 0
    n_parts_per_op: int = 0
    n_trials: int = 0


def compute_nested_grr(
    records:     List[MeasurementRecord],
    n_operators: int,
    n_trials:    int,
) -> NestedGRRResults:
    """
    Nested GR&R for destructive / non-reproducible samples.
    Each operator measures a unique set of parts; parts are not crossed.
    Variance decomposition via ANOVA-style nested model.
    """
    from collections import defaultdict

    op_map: Dict[str, List[MeasurementRecord]] = defaultdict(list)
    for rec in records:
        op_map[rec.operator].append(rec)

    n_parts_per_op = len(next(iter(op_map.values())))

    # Within-operator repeatability: pooled variance of trial-to-trial ranges
    all_within_vars = []
    op_part_means: Dict[str, List[float]] = {}
    for op_name, recs in op_map.items():
        part_means  = [r.mean for r in recs]
        op_part_means[op_name] = part_means
        for r in recs:
            vals = np.array(r.trials, dtype=float)
            if len(vals) > 1:
                all_within_vars.append(float(np.var(vals, ddof=1)))

    sigma2_repeatability = float(np.mean(all_within_vars)) if all_within_vars else 0.0

    # Between-parts within operator: variance of part means per operator, pooled
    within_op_part_vars = []
    for pm in op_part_means.values():
        if len(pm) > 1:
            within_op_part_vars.append(float(np.var(pm, ddof=1)))
    sigma2_parts_within = float(np.mean(within_op_part_vars)) if within_op_part_vars else 0.0
    sigma2_operator_parts = max(0.0, sigma2_parts_within - sigma2_repeatability / n_trials)

    # Between-operator variance from operator grand means
    op_grand_means = [float(np.mean(pm)) for pm in op_part_means.values()]
    sigma2_operator = float(np.var(op_grand_means, ddof=1)) if len(op_grand_means) > 1 else 0.0
    sigma2_operator = max(0.0, sigma2_operator - sigma2_operator_parts / n_parts_per_op)

    # 5.15-sigma study variation
    ev  = 5.15 * math.sqrt(sigma2_repeatability)
    av  = 5.15 * math.sqrt(sigma2_operator)
    grr = math.sqrt(ev**2 + av**2)
    pv  = 5.15 * math.sqrt(max(0.0, sigma2_operator_parts))
    tv  = math.sqrt(grr**2 + pv**2) if (grr**2 + pv**2) > 0 else 0.0

    pct_ev  = (ev  / tv * 100) if tv > 0 else 0.0
    pct_av  = (av  / tv * 100) if tv > 0 else 0.0
    pct_grr = (grr / tv * 100) if tv > 0 else 0.0
    pct_pv  = (pv  / tv * 100) if tv > 0 else 0.0
    ndc     = int(math.floor(1.41 * pv / grr)) if grr > 0 else 0

    status = ("ACCEPTABLE" if pct_grr <= GRR_ACCEPTABLE_THRESHOLD
              else "MARGINAL" if pct_grr <= GRR_MARGINAL_THRESHOLD
              else "UNACCEPTABLE")

    return NestedGRRResults(
        ev=ev, av=av, grr=grr, pv=pv, tv=tv,
        pct_ev=pct_ev, pct_av=pct_av, pct_grr=pct_grr, pct_pv=pct_pv,
        ndc=ndc, status=status,
        n_operators=n_operators,
        n_parts_per_op=n_parts_per_op,
        n_trials=n_trials,
    )


# ---------------------------------------------------------------------------
# Attribute GR&R  (Task 4D)
# ---------------------------------------------------------------------------

@dataclass
class AttributeGRRResults:
    operators:             List[str]
    within_op_agreement:   Dict[str, float]   # % same decision across trials
    between_op_agreement:  float              # % all operators agree on same part
    kappa:                 Dict[str, float]   # per-operator kappa vs. majority vote
    effectiveness:         Optional[Dict[str, float]] = None  # vs. reference
    overall_effectiveness: Optional[float] = None
    status:                str = ""           # ACCEPTABLE / MARGINAL / UNACCEPTABLE


def compute_attribute_grr(
    records:    List[MeasurementRecord],
    references: Optional[Dict[str, int]] = None,
) -> AttributeGRRResults:
    """
    Attribute Agreement Analysis for go/no-go, pass/fail data.
    Trial values must be 0 or 1. References: {part_id: 0_or_1} if available.
    """
    from collections import defaultdict

    # Group by operator and part
    op_part: Dict[str, Dict[str, List[int]]] = defaultdict(lambda: defaultdict(list))
    for rec in records:
        for trial_val in rec.trials:
            op_part[rec.operator][rec.part].append(int(round(trial_val)))

    operators = sorted(op_part.keys())
    parts     = sorted({rec.part for rec in records})

    # Within-operator agreement: operator agrees with self across all trials for a part
    within_agree: Dict[str, float] = {}
    for op in operators:
        agree_count = sum(
            1 for p in parts
            if len(set(op_part[op][p])) == 1
        )
        within_agree[op] = 100.0 * agree_count / len(parts)

    # Between-operator agreement: all operators give the same majority decision for a part
    between_count = 0
    for p in parts:
        # Majority decision per operator
        op_decisions = []
        for op in operators:
            trials = op_part[op].get(p, [])
            if trials:
                op_decisions.append(1 if sum(trials) > len(trials) / 2 else 0)
        if len(set(op_decisions)) == 1:
            between_count += 1
    between_agree = 100.0 * between_count / len(parts)

    # Kappa per operator vs. majority vote across all operators
    kappa_scores: Dict[str, float] = {}
    # Build majority reference from all operators
    majority_ref: Dict[str, int] = {}
    for p in parts:
        votes = []
        for op in operators:
            t = op_part[op].get(p, [])
            if t:
                votes.append(1 if sum(t) > len(t) / 2 else 0)
        majority_ref[p] = 1 if sum(votes) > len(votes) / 2 else 0

    for op in operators:
        op_decisions = {p: (1 if sum(op_part[op].get(p, [0])) > len(op_part[op].get(p, [0])) / 2 else 0)
                        for p in parts}
        n_agree = sum(1 for p in parts if op_decisions[p] == majority_ref[p])
        p_o   = n_agree / len(parts)
        p_pos = sum(majority_ref.values()) / len(parts)
        p_neg = 1.0 - p_pos
        p_e   = p_pos * (sum(op_decisions.values()) / len(parts)) + \
                p_neg * ((len(parts) - sum(op_decisions.values())) / len(parts))
        kappa = (p_o - p_e) / (1.0 - p_e) if (1.0 - p_e) > 0 else 0.0
        kappa_scores[op] = round(kappa, 3)

    # Effectiveness vs. external reference
    effectiveness: Optional[Dict[str, float]] = None
    overall_eff: Optional[float] = None
    if references:
        effectiveness = {}
        for op in operators:
            match = sum(
                1 for p in parts
                if p in references and
                (1 if sum(op_part[op].get(p, [0])) > len(op_part[op].get(p, [0])) / 2 else 0)
                == references[p]
            )
            ref_parts = [p for p in parts if p in references]
            effectiveness[op] = 100.0 * match / len(ref_parts) if ref_parts else 0.0
        overall_eff = float(np.mean(list(effectiveness.values()))) if effectiveness else None

    # Status from overall effectiveness or between-operator agreement
    score = overall_eff if overall_eff is not None else between_agree
    status = ("ACCEPTABLE" if score >= 90 else "MARGINAL" if score >= 80 else "UNACCEPTABLE")

    return AttributeGRRResults(
        operators=operators,
        within_op_agreement=within_agree,
        between_op_agreement=between_agree,
        kappa=kappa_scores,
        effectiveness=effectiveness,
        overall_effectiveness=overall_eff,
        status=status,
    )


def print_attribute_report(attr: AttributeGRRResults) -> None:
    """Console output for attribute GR&R."""
    w = 62
    print()
    print("=" * w)
    print("  ATTRIBUTE AGREEMENT ANALYSIS".center(w))
    print("=" * w)
    print(f"  {'Operator':<20} {'Within-Op%':>12}  {'Kappa':>8}")
    print(f"  {'-' * 45}")
    for op in attr.operators:
        kval = attr.kappa.get(op, 0.0)
        print(f"  {op:<20} {attr.within_op_agreement[op]:>11.1f}%  {kval:>8.3f}")
    print(f"\n  Between-operator agreement: {attr.between_op_agreement:.1f}%")
    if attr.overall_effectiveness is not None:
        print(f"  Overall effectiveness:      {attr.overall_effectiveness:.1f}%")
        if attr.effectiveness:
            for op, eff in attr.effectiveness.items():
                print(f"    {op}: {eff:.1f}%")
    print(f"\n  STATUS: {attr.status}")
    print(f"  (>=90% Acceptable | 80-90% Marginal | <80% Unacceptable)")
    print("=" * w)


# ---------------------------------------------------------------------------
# Run Chart + Nelson Rules  (Task 4F)
# ---------------------------------------------------------------------------

NELSON_RULES = {
    1: "Rule 1: Point beyond 3σ",
    2: "Rule 2: 9 consecutive points on same side of mean",
    5: "Rule 5: 2 of 3 consecutive points beyond 2σ on same side",
    6: "Rule 6: 4 of 5 consecutive points beyond 1σ on same side",
}


def detect_nelson_violations(values: List[float]) -> List[Tuple[int, int, str]]:
    """
    Detect Nelson rules 1, 2, 5, 6 on a list of values.
    Returns list of (rule_number, index, description).
    """
    arr    = np.array(values, dtype=float)
    mean   = arr.mean()
    sigma  = arr.std(ddof=1) if len(arr) > 1 else 1.0
    z      = (arr - mean) / sigma if sigma > 0 else np.zeros_like(arr)
    violations: List[Tuple[int, int, str]] = []

    for i, zi in enumerate(z):
        # Rule 1: beyond 3σ
        if abs(zi) > 3:
            violations.append((1, i, NELSON_RULES[1]))

    # Rule 2: 9 consecutive same side
    signs = np.sign(z)
    for i in range(8, len(signs)):
        window = signs[i-8:i+1]
        if len(set(window)) == 1 and window[0] != 0:
            violations.append((2, i, NELSON_RULES[2]))

    # Rule 5: 2 of 3 beyond 2σ same side
    for i in range(2, len(z)):
        window = z[i-2:i+1]
        pos = sum(1 for v in window if v >  2)
        neg = sum(1 for v in window if v < -2)
        if pos >= 2 or neg >= 2:
            violations.append((5, i, NELSON_RULES[5]))

    # Rule 6: 4 of 5 beyond 1σ same side
    for i in range(4, len(z)):
        window = z[i-4:i+1]
        pos = sum(1 for v in window if v >  1)
        neg = sum(1 for v in window if v < -1)
        if pos >= 4 or neg >= 4:
            violations.append((6, i, NELSON_RULES[6]))

    return violations


def _chart_run(
    run_values: List[float],
    run_labels: Optional[List[str]] = None,
    violations: Optional[List[Tuple[int, int, str]]] = None,
) -> Image:
    """Time-series run chart with Nelson rule violation markers."""
    n      = len(run_values)
    x      = np.arange(1, n + 1)
    mean   = float(np.mean(run_values))
    sigma  = float(np.std(run_values, ddof=1)) if n > 1 else 0.0

    fig, ax = plt.subplots(figsize=(7.0, 3.2), facecolor="white")
    ax.plot(x, run_values, marker="o", markersize=4, color=NAVY,
            linewidth=1.2, zorder=3)
    ax.axhline(mean, color=GREY,   linestyle="-",  linewidth=1.0,
               label=f"Mean = {mean:.4f}")
    ax.axhline(mean + 3*sigma, color=RED,  linestyle="--", linewidth=1.0,
               label=f"+3σ = {mean + 3*sigma:.4f}")
    ax.axhline(mean - 3*sigma, color=RED,  linestyle="--", linewidth=1.0,
               label=f"-3σ = {mean - 3*sigma:.4f}")

    if violations:
        flagged = {v[1] for v in violations}
        flag_x  = [x[i] for i in flagged if i < n]
        flag_y  = [run_values[i] for i in flagged if i < n]
        ax.scatter(flag_x, flag_y, color=RED, s=80, zorder=5, label="Nelson violation")

    if run_labels:
        ax.set_xticks(x[::max(1, n // 20)])
        ax.set_xticklabels(run_labels[::max(1, n // 20)], fontsize=7, rotation=45)
    ax.set_xlabel("Run order", fontsize=9)
    ax.set_ylabel("Measurement", fontsize=9)
    ax.set_title("Run Chart — Time Series Stability", fontsize=10,
                 fontweight="bold", pad=8)
    ax.legend(fontsize=7.5, ncol=2)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return _fig_to_image(fig, 7.0, 3.2)


# ---------------------------------------------------------------------------
# Multi-study Comparison  (Task 4G)
# ---------------------------------------------------------------------------

@dataclass
class StudySummary:
    label:    str
    pct_grr:  float
    ndc:      int
    pct_ev:   float
    pct_av:   float
    pct_pv:   float
    status:   str


def _chart_comparison(summaries: List[StudySummary]) -> Image:
    """Side-by-side bar chart for multi-study comparison."""
    labels   = [s.label for s in summaries]
    pct_grrs = [s.pct_grr for s in summaries]
    bar_colors = [
        RED if s.pct_grr > 30 else ORANGE if s.pct_grr > 10 else GREEN
        for s in summaries
    ]

    fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.5), facecolor="white")

    # Left: %GRR bars
    ax = axes[0]
    bars = ax.bar(range(len(labels)), pct_grrs, color=bar_colors, width=0.5, zorder=3)
    ax.axhline(10, color=GREEN, linestyle="--", linewidth=1.2, label="10% (Accept)")
    ax.axhline(30, color=RED,   linestyle="--", linewidth=1.2, label="30% (Reject)")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=8, rotation=20, ha="right")
    ax.set_ylabel("%GRR", fontsize=9)
    ax.set_title("%GR&R by Study", fontsize=10, fontweight="bold", pad=6)
    ax.legend(fontsize=7.5)
    for bar, val in zip(bars, pct_grrs):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f"{val:.1f}%", ha="center", va="bottom", fontsize=7.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Right: stacked EV / AV / PV
    ax2 = axes[1]
    x    = np.arange(len(labels))
    ev_v = [s.pct_ev for s in summaries]
    av_v = [s.pct_av for s in summaries]
    pv_v = [s.pct_pv for s in summaries]
    ax2.bar(x, ev_v, 0.45, label="EV",  color=TEAL,   zorder=3)
    ax2.bar(x, av_v, 0.45, bottom=ev_v, label="AV",   color=ORANGE, zorder=3)
    ax2.bar(x, pv_v, 0.45,
            bottom=[e + a for e, a in zip(ev_v, av_v)],
            label="PV", color=NAVY, zorder=3)
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, fontsize=8, rotation=20, ha="right")
    ax2.set_ylabel("% Study Variation", fontsize=9)
    ax2.set_title("Variance Components by Study", fontsize=10, fontweight="bold", pad=6)
    ax2.legend(fontsize=7.5)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)

    fig.tight_layout()
    return _fig_to_image(fig, 9.0, 3.5)


def build_comparison_report(
    summaries:   List[StudySummary],
    output_path: Path,
) -> None:
    """Generate a multi-study comparison PDF."""
    doc = SimpleDocTemplate(
        str(output_path), pagesize=letter,
        leftMargin=0.75*inch, rightMargin=0.75*inch,
        topMargin=0.65*inch, bottomMargin=0.80*inch,
        title="GR&R Multi-Study Comparison",
    )
    s_title   = _ps("T",  fontSize=14, fontName="Helvetica-Bold",
                          textColor=_C_DARK, alignment=1, spaceAfter=6)
    s_section = _ps("Se", fontSize=10, fontName="Helvetica-Bold",
                          textColor=_C_DARK, spaceBefore=8, spaceAfter=4)
    story = [
        Paragraph("GR&R Multi-Study Comparison", s_title),
        HRFlowable(width="100%", thickness=1.5, color=_C_DARK),
        Spacer(1, 0.15*inch),
    ]

    # Summary table
    story.append(Paragraph("Study Comparison Summary", s_section))
    hdr = ["Study", "%GRR", "EV%", "AV%", "PV%", "ndc", "Verdict"]
    rows = [hdr] + [
        [s.label, f"{s.pct_grr:.1f}%", f"{s.pct_ev:.1f}%",
         f"{s.pct_av:.1f}%", f"{s.pct_pv:.1f}%", str(s.ndc), s.status]
        for s in summaries
    ]
    tbl = Table(rows, colWidths=[1.8*inch, 0.85*inch, 0.75*inch,
                                  0.75*inch, 0.75*inch, 0.6*inch, 1.2*inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), _C_DARK),
        ("TEXTCOLOR",      (0, 0), (-1, 0), _C_WHITE),
        ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_C_LGRAY, _C_WHITE]),
        ("GRID",           (0, 0), (-1, -1), 0.4, _C_BORD),
        ("ALIGN",          (1, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",     (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
    ]))
    story += [tbl, Spacer(1, 0.15*inch)]

    story.append(Paragraph("Comparison Charts", s_section))
    story.append(_chart_comparison(summaries))

    doc.build(story)
    print(f"[+] Comparison report written to: {output_path}")


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
    p.add_argument("--usl", type=float, default=None, metavar="USL",
                   help="Upper spec limit (alternative to --tolerance for asymmetric specs)")
    p.add_argument("--lsl", type=float, default=None, metavar="LSL",
                   help="Lower spec limit (alternative to --tolerance for asymmetric specs)")
    p.add_argument("--title",     type=str, default="GR&R Study Report", metavar="TITLE",
                   help='Report title (default: "GR&R Study Report")')
    p.add_argument("--equipment", "-e", type=str, default="Unspecified Gage", metavar="NAME",
                   help="Equipment / gage identifier (e.g. 'Mitutoyo 293-340-30 SN-1234')")
    p.add_argument("--operator",  type=str, default="Quality Engineering", metavar="NAME",
                   help="Name of QE or team who performed the study")
    p.add_argument("--generate-sample", action="store_true",
                   help="Generate a sample 10-part x 3-operator x 3-trial CSV before analysis")
    p.add_argument("--study-type", choices=["crossed", "nested", "linearity", "bias"],
                   default="crossed",
                   help="Study type: crossed (default), nested (destructive), linearity, bias")
    p.add_argument("--reference-values", type=str, default=None, metavar="CSV_LIST",
                   help="Comma-separated known reference values (for --study-type linearity/bias)")
    p.add_argument("--attribute", action="store_true",
                   help="Attribute agreement analysis mode (trial values must be 0 or 1)")
    p.add_argument("--reference-csv", type=Path, default=None, metavar="REF_CSV",
                   help="CSV with Part,Reference columns (0/1) for attribute effectiveness")
    p.add_argument("--run-order", type=str, default=None, metavar="COLUMN",
                   help="Column name in the CSV containing run order; enables run chart + Nelson rules")
    p.add_argument("--compare", nargs="+", type=Path, default=None, metavar="CSV",
                   help="Two or more CSV files for multi-study comparison report")
    p.add_argument("--version", "-v", action="version",
                   version=f"%(prog)s {__version__}")
    return p.parse_args()


def main() -> None:
    """Main entry point -- orchestrates sample generation, analysis, and reporting."""
    args = parse_args()

    # ── Multi-study comparison mode ─────────────────────────────────────────
    if args.compare:
        summaries: List[StudySummary] = []
        for csv_path in args.compare:
            recs, np_, no_, nt_ = load_data(csv_path)
            r = compute_grr(recs, np_, no_, nt_)
            summaries.append(StudySummary(
                label=csv_path.stem,
                pct_grr=r.pct_grr, ndc=r.ndc,
                pct_ev=r.pct_ev, pct_av=r.pct_av, pct_pv=r.pct_pv,
                status=r.status,
            ))
        out = args.output or Path("grr_comparison.pdf")
        build_comparison_report(summaries, out)
        return

    if args.generate_sample:
        generate_sample_data(args.input)

    # ── Attribute mode ──────────────────────────────────────────────────────
    if args.attribute:
        records, _, _, _ = load_data(args.input)
        refs: Optional[Dict[str, int]] = None
        if args.reference_csv:
            try:
                ref_df = pd.read_csv(args.reference_csv)
                refs = {str(r["Part"]): int(r["Reference"]) for _, r in ref_df.iterrows()}
            except Exception as exc:
                sys.exit(f"[ERROR] Failed to read reference CSV: {exc}")
        attr = compute_attribute_grr(records, refs)
        print_attribute_report(attr)
        return

    # ── Linearity / Bias modes ──────────────────────────────────────────────
    if args.study_type in ("linearity", "bias"):
        records, n_parts_, _, _ = load_data(args.input)
        if not args.reference_values:
            sys.exit("[ERROR] --reference-values is required for linearity/bias study types.")
        ref_vals = [float(v.strip()) for v in args.reference_values.split(",")]

        # For linearity: use per-part grand means (one mean per unique part in part order)
        from collections import defaultdict as _dd
        part_order = sorted({r.part for r in records})
        part_meas_map: Dict[str, List[float]] = _dd(list)
        for r in records:
            part_meas_map[r.part].extend(r.trials)
        # Bias mode: use all individual trial measurements vs. single reference
        all_meas = [t for rec in records for t in rec.trials]
        # Linearity mode: per-part mean measurements
        part_means_lin = [float(np.mean(part_meas_map[p])) for p in part_order]

        if args.study_type == "linearity":
            lin = compute_linearity(part_means_lin, ref_vals, tolerance=args.tolerance)
            print(f"\nLinearity Study:")
            print(f"  Slope     : {lin.slope:.6f}")
            print(f"  Intercept : {lin.intercept:.6f}")
            print(f"  R²        : {lin.r_squared:.4f}")
            if lin.slope_p_value is not None:
                sig = "statistically significant" if lin.slope_p_value < 0.05 else "NOT significant"
                print(f"  Slope p   : {lin.slope_p_value:.4f} ({sig} at alpha=0.05)")
            if lin.linearity_pct is not None:
                print(f"  Linearity : {lin.linearity_pct:.2f}% of tolerance")
        else:
            ref_single = ref_vals[0]
            bres = compute_bias(all_meas, ref_single, tolerance=args.tolerance)
            print(f"\nBias Study (reference = {ref_single}):")
            print(f"  Bias      : {bres.bias:.6f}")
            print(f"  %Bias     : {bres.bias_pct:.2f}% of tolerance")
            print(f"  t-stat    : {bres.t_statistic:.4f}")
            if bres.p_value is not None:
                print(f"  p-value   : {bres.p_value:.4f}")
            print(f"  95% CI    : [{bres.ci_95_lower:.6f}, {bres.ci_95_upper:.6f}]")
            verdict = "ACCEPTABLE" if bres.bias_pct <= 1.0 else "UNACCEPTABLE"
            print(f"  Verdict   : {verdict} (%bias {'<=' if bres.bias_pct <= 1.0 else '>'} 1%)")
        return

    # ── Default to PDF output when neither --output nor --dashboard is given ─
    pdf_path = args.output or (
        args.input.with_name(args.input.stem + "_grr_report.pdf")
        if not args.dashboard else None
    )

    records, n_parts, n_operators, n_trials = load_data(args.input)

    # ── Nested GR&R ─────────────────────────────────────────────────────────
    if args.study_type == "nested":
        nres = compute_nested_grr(records, n_operators, n_trials)
        print(f"\nNested GR&R (destructive study):")
        print(f"  EV  : {nres.ev:.5f} ({nres.pct_ev:.1f}%)")
        print(f"  AV  : {nres.av:.5f} ({nres.pct_av:.1f}%)")
        print(f"  GRR : {nres.grr:.5f} ({nres.pct_grr:.1f}%)")
        print(f"  PV  : {nres.pv:.5f} ({nres.pct_pv:.1f}%)")
        print(f"  TV  : {nres.tv:.5f}")
        print(f"  ndc : {nres.ndc}")
        print(f"  STATUS: {nres.status}")
        return

    res = compute_grr(records, n_parts, n_operators, n_trials,
                      tolerance=args.tolerance, usl=args.usl, lsl=args.lsl)

    # ── Run chart (if RunOrder column requested) ─────────────────────────────
    run_chart_img: Optional[Image] = None
    nelson_violations: List[Tuple[int, int, str]] = []
    if args.run_order:
        try:
            df_run = pd.read_csv(args.input)
            if args.run_order in df_run.columns:
                df_run = df_run.sort_values(args.run_order)
                trial_cols = [c for c in df_run.columns
                              if c.lower().startswith("trial")]
                run_vals = df_run[trial_cols].values.flatten().tolist()
                run_vals_f = [float(v) for v in run_vals if pd.notna(v)]
                nelson_violations = detect_nelson_violations(run_vals_f)
                run_chart_img = _chart_run(run_vals_f, violations=nelson_violations)
                if nelson_violations:
                    print(f"[!] Nelson rule violations detected: {len(nelson_violations)}")
                    for rule, idx, desc in nelson_violations[:5]:
                        print(f"    Index {idx}: {desc}")
        except Exception as exc:
            print(f"[WARN] Could not build run chart: {exc}")

    print_console_report(res, args.equipment, args.operator)

    # Print CI summary
    print(f"  95% CI on GR&R: [{res.grr_ci95[0]:.5f}, {res.grr_ci95[1]:.5f}]")
    if res.ndc_tol is not None:
        print(f"  ndc (tolerance-based): {res.ndc_tol:.1f}")

    if pdf_path:
        build_pdf_report(res, pdf_path, args.equipment, args.operator, args.title)

    if args.dashboard:
        build_dashboard(res, args.dashboard, args.equipment, args.operator, args.title)


if __name__ == "__main__":
    main()
