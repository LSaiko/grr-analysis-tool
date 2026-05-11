"""
grr_tool.py — Gauge Repeatability & Reproducibility (GR&R) Analysis Tool
=========================================================================
Follows AIAG Measurement Systems Analysis (MSA) 4th Edition methodology.

Intended use: Medical device manufacturing quality engineering.
Regulatory context: 21 CFR 820.72 — Inspection, Measuring, and Test Equipment.

Author note:
    This tool automates the AIAG crossed GR&R study, the industry-standard
    method for evaluating measurement system variation in manufacturing
    environments. It separates total measurement variation into:
      - Equipment Variation (EV): repeatability — variation within one operator
      - Appraiser Variation (AV): reproducibility — variation between operators
      - Part Variation (PV): actual part-to-part variation
    The goal is to confirm the measurement system's error is small relative
    to total variation before using it for product acceptance decisions.

Usage examples:
    # Generate sample data and run analysis:
    python grr_tool.py --generate-sample --input sample_grr.csv \
        --output grr_report.pdf --equipment "Mitutoyo 293-340-30" \
        --operator "J. Martinez"

    # Run on existing CSV:
    python grr_tool.py --input my_data.csv --output report.pdf \
        --equipment "Digital Caliper #3" --operator "QE Team"
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# AIAG MSA 4th Edition Constants
# ---------------------------------------------------------------------------
# K1: control chart constant d2* for within-operator range variation.
#   Indexed by number of trials. For 3 trials: K1 = 1/d2* = 1/1.6926 ≈ 0.5908
#   Then EV = R̄̄ × (5.15 / d2*) for 99% study variation
#   AIAG shorthand uses K1 = 3.05 for 3 trials (= 5.15 / 1.6926 rounded).
K1_BY_TRIALS: Dict[int, float] = {2: 4.56, 3: 3.05, 4: 2.50, 5: 2.21}

# K2: constant for appraiser variation, based on number of operators.
#   K2 = 5.15 / d2*(operators). For 3 operators: 5.15 / 1.9062 ≈ 2.70.
K2_BY_OPERATORS: Dict[int, float] = {2: 3.65, 3: 2.70, 4: 2.30, 5: 2.08}

# K3: constant for part variation, based on number of parts.
#   K3 = 5.15 / d2*(parts). For 10 parts: 5.15 / 3.1796 ≈ 1.62.
K3_BY_PARTS: Dict[int, float] = {
    2: 3.65, 3: 2.70, 4: 2.30, 5: 2.08,
    6: 1.93, 7: 1.82, 8: 1.74, 9: 1.67, 10: 1.62,
}

# Acceptance thresholds per AIAG MSA 4th Ed., Section III
GRR_ACCEPTABLE_THRESHOLD = 10.0   # %GR&R ≤ 10% → Acceptable
GRR_MARGINAL_THRESHOLD   = 30.0   # %GR&R ≤ 30% → Marginal
NDC_MINIMUM              = 5      # ndc ≥ 5 required for adequate discrimination

# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class MeasurementRecord:
    """Represents one row of GR&R study data."""
    part:     str
    operator: str
    trials:   List[float]  # length == number of trials

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
    part_ranges: List[float]    # range of each part's trials for this operator
    part_means:  List[float]    # mean of each part's trials for this operator
    r_bar:       float = 0.0    # R̄ = average range across all parts
    x_bar:       float = 0.0    # X̄ = grand mean for this operator

    def __post_init__(self):
        self.r_bar = sum(self.part_ranges) / len(self.part_ranges)
        self.x_bar = sum(self.part_means)  / len(self.part_means)


@dataclass
class GRRResults:
    """All computed GR&R metrics per AIAG MSA 4th Edition."""
    # Raw inputs stored for reporting
    grand_mean:      float = 0.0
    r_bar_bar:       float = 0.0   # R̄̄ = average of all operator R̄ values
    x_diff:          float = 0.0   # max(X̄ operator) - min(X̄ operator)
    rp:              float = 0.0   # range of part averages

    # Variance components (study variation units, not sigma)
    ev:  float = 0.0   # Equipment Variation (repeatability)
    av:  float = 0.0   # Appraiser Variation (reproducibility)
    grr: float = 0.0   # Combined GR&R
    pv:  float = 0.0   # Part Variation
    tv:  float = 0.0   # Total Variation

    # Percentage contributions
    pct_ev:  float = 0.0
    pct_av:  float = 0.0
    pct_grr: float = 0.0
    pct_pv:  float = 0.0

    # Quality indicator
    ndc:    float = 0.0    # Number of Distinct Categories
    status: str   = ""     # ACCEPTABLE / MARGINAL / UNACCEPTABLE

    operator_stats: List[OperatorStats] = field(default_factory=list)

# ---------------------------------------------------------------------------
# Sample Data Generator
# ---------------------------------------------------------------------------

def generate_sample_data(output_path: Path) -> None:
    """
    Generate a realistic 10-part × 3-operator × 3-trial GR&R dataset and
    write it to a CSV file.

    The simulated measurements follow a model:
        measurement = true_part_value + operator_bias + random_noise

    True part values are spread across a realistic tolerance window to simulate
    a capable process. Operator biases introduce reproducibility error.
    Gaussian noise models the gage's inherent repeatability error.

    Args:
        output_path: Destination path for the generated CSV file.
    """
    random.seed(42)  # reproducible for demo purposes

    # Simulate 10 parts with true values varying ~±0.03 mm around nominal
    nominal = 10.000  # mm — arbitrary nominal dimension
    true_values = [round(nominal + random.uniform(-0.03, 0.03), 4) for _ in range(10)]

    # Operator biases (reproducibility error component)
    operator_biases = {"Alice": 0.0, "Bob": 0.003, "Carol": -0.002}

    # Gage noise standard deviation (repeatability error component)
    noise_sigma = 0.002  # mm

    parts     = [f"P{i+1:02d}" for i in range(10)]
    operators = list(operator_biases.keys())

    rows = [["Part", "Operator", "Trial1", "Trial2", "Trial3"]]
    for part_name, true_val in zip(parts, true_values):
        for op in operators:
            bias = operator_biases[op]
            t1 = round(true_val + bias + random.gauss(0, noise_sigma), 4)
            t2 = round(true_val + bias + random.gauss(0, noise_sigma), 4)
            t3 = round(true_val + bias + random.gauss(0, noise_sigma), 4)
            rows.append([part_name, op, t1, t2, t3])

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    print(f"[+] Sample data written to: {output_path}")

# ---------------------------------------------------------------------------
# Data Loading & Validation
# ---------------------------------------------------------------------------

def load_data(csv_path: Path) -> Tuple[List[MeasurementRecord], int, int, int]:
    """
    Load and validate GR&R study data from a CSV file.

    Expected columns: Part, Operator, Trial1, Trial2, ..., TrialN
    At minimum Trial1 and Trial2 must be present (2 trials minimum).

    Args:
        csv_path: Path to the input CSV file.

    Returns:
        Tuple of (records, n_parts, n_operators, n_trials).

    Raises:
        SystemExit on validation failure.
    """
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        sys.exit(f"[ERROR] Input file not found: {csv_path}")
    except Exception as e:
        sys.exit(f"[ERROR] Failed to read CSV: {e}")

    # Detect trial columns dynamically (Trial1, Trial2, ...)
    trial_cols = [c for c in df.columns if c.lower().startswith("trial")]
    if len(trial_cols) < 2:
        sys.exit("[ERROR] CSV must have at least Trial1 and Trial2 columns.")

    required = {"Part", "Operator"} | set(trial_cols)
    missing = required - set(df.columns)
    if missing:
        sys.exit(f"[ERROR] Missing columns: {missing}")

    # Convert trial columns to numeric, coercing errors
    for col in trial_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if df[trial_cols].isna().any().any():
        sys.exit("[ERROR] Non-numeric values found in trial columns.")

    records = [
        MeasurementRecord(
            part=str(row["Part"]),
            operator=str(row["Operator"]),
            trials=[row[c] for c in trial_cols],
        )
        for _, row in df.iterrows()
    ]

    parts     = sorted(df["Part"].unique())
    operators = sorted(df["Operator"].unique())
    n_parts     = len(parts)
    n_operators = len(operators)
    n_trials    = len(trial_cols)

    # Validate study design constants are supported
    if n_trials not in K1_BY_TRIALS:
        sys.exit(f"[ERROR] Unsupported trial count {n_trials}. Supported: {list(K1_BY_TRIALS.keys())}")
    if n_operators not in K2_BY_OPERATORS:
        sys.exit(f"[ERROR] Unsupported operator count {n_operators}. Supported: {list(K2_BY_OPERATORS.keys())}")
    if n_parts not in K3_BY_PARTS:
        sys.exit(f"[ERROR] Unsupported part count {n_parts}. Supported: {list(K3_BY_PARTS.keys())}")

    print(f"[+] Loaded {len(records)} records: "
          f"{n_parts} parts × {n_operators} operators × {n_trials} trials")
    return records, n_parts, n_operators, n_trials

# ---------------------------------------------------------------------------
# GR&R Calculations (AIAG MSA 4th Edition)
# ---------------------------------------------------------------------------

def compute_grr(
    records:     List[MeasurementRecord],
    n_parts:     int,
    n_operators: int,
    n_trials:    int,
) -> GRRResults:
    """
    Perform the full AIAG crossed GR&R calculation.

    AIAG Method Overview
    --------------------
    The AIAG MSA manual defines study variation as 5.15 sigma (99% of the
    normal distribution). All variation components are expressed in those
    units, then compared as percentages of total variation.

    Step 1 — Build per-operator statistics
    Step 2 — Compute R̄̄ (equipment / repeatability variation source)
    Step 3 — Compute X̄_diff (appraiser / reproducibility variation source)
    Step 4 — Apply K constants to convert ranges to 5.15-sigma study variation
    Step 5 — Propagate through variance equations to get TV
    Step 6 — Compute percentage contributions and ndc

    Args:
        records:     Flat list of MeasurementRecord objects.
        n_parts:     Number of unique parts in the study.
        n_operators: Number of unique operators.
        n_trials:    Number of repeated trials per operator per part.

    Returns:
        Populated GRRResults dataclass.
    """
    results = GRRResults()

    # Retrieve AIAG constants for this study design
    k1 = K1_BY_TRIALS[n_trials]
    k2 = K2_BY_OPERATORS[n_operators]
    k3 = K3_BY_PARTS[n_parts]

    # ----- STEP 1: Build per-operator statistics -----
    # Group records by operator → per-part ranges and means
    operator_map: Dict[str, List[MeasurementRecord]] = {}
    for rec in records:
        operator_map.setdefault(rec.operator, []).append(rec)

    op_stats_list: List[OperatorStats] = []
    for op_name, op_records in sorted(operator_map.items()):
        part_ranges = [r.range_ for r in op_records]
        part_means  = [r.mean   for r in op_records]
        op_stats_list.append(OperatorStats(
            name=op_name,
            part_ranges=part_ranges,
            part_means=part_means,
        ))

    results.operator_stats = op_stats_list

    # ----- STEP 2: R̄̄ — overall average range (equipment source) -----
    # R̄̄ = mean of each operator's average range
    # This captures how consistently each operator repeats measurements.
    r_bars   = [op.r_bar for op in op_stats_list]
    r_bar_bar = sum(r_bars) / len(r_bars)
    results.r_bar_bar = r_bar_bar

    # ----- STEP 3: X̄_diff — spread between operator grand means -----
    # X̄_diff = max(operator mean) - min(operator mean)
    # This captures systematic offset between operators (reproducibility).
    op_grand_means = [op.x_bar for op in op_stats_list]
    x_diff          = max(op_grand_means) - min(op_grand_means)
    results.x_diff  = x_diff

    # ----- STEP 4a: Grand mean of all measurements -----
    all_measurements = [t for rec in records for t in rec.trials]
    results.grand_mean = sum(all_measurements) / len(all_measurements)

    # ----- STEP 4b: Part variation — range of part averages -----
    # Compute the average measurement for each part (across all operators & trials)
    part_map: Dict[str, List[MeasurementRecord]] = {}
    for rec in records:
        part_map.setdefault(rec.part, []).append(rec)

    part_averages = [
        sum(r.mean for r in recs) / len(recs)
        for recs in part_map.values()
    ]
    rp = max(part_averages) - min(part_averages)
    results.rp = rp

    # ----- STEP 5: Apply AIAG K-constants to get study variation -----
    # EV (Equipment Variation / Repeatability)
    #   EV = R̄̄ × K1
    #   Reflects the gage's inherent inability to repeat the same reading.
    ev = r_bar_bar * k1
    results.ev = ev

    # AV (Appraiser Variation / Reproducibility)
    #   AV = sqrt(max(0, (X̄_diff × K2)² - (EV²/(n×r))))
    #   n = number of parts, r = number of trials
    #   The subtracted term corrects AV for the repeatability component
    #   already embedded in X̄_diff when sample sizes are finite.
    av_sq = (x_diff * k2) ** 2 - (ev ** 2 / (n_parts * n_trials))
    av = math.sqrt(max(0.0, av_sq))
    results.av = av

    # GR&R — combined measurement system variation
    grr = math.sqrt(ev ** 2 + av ** 2)
    results.grr = grr

    # PV (Part Variation)
    pv = rp * k3
    results.pv = pv

    # TV (Total Variation)
    tv = math.sqrt(grr ** 2 + pv ** 2)
    results.tv = tv

    # ----- STEP 6: Percentage contributions -----
    # Per AIAG: %XX = (XX / TV) × 100
    if tv > 0:
        results.pct_ev  = (ev  / tv) * 100
        results.pct_av  = (av  / tv) * 100
        results.pct_grr = (grr / tv) * 100
        results.pct_pv  = (pv  / tv) * 100

    # ndc — Number of Distinct Categories
    #   ndc = 1.41 × (PV / GR&R)
    #   Represents how many non-overlapping data groups the gage can resolve.
    #   AIAG requires ndc ≥ 5 for the measurement system to be adequate.
    if grr > 0:
        results.ndc = 1.41 * (pv / grr)
    else:
        results.ndc = float("inf")

    # ----- STEP 7: Acceptance evaluation -----
    if results.pct_grr <= GRR_ACCEPTABLE_THRESHOLD:
        results.status = "ACCEPTABLE"
    elif results.pct_grr <= GRR_MARGINAL_THRESHOLD:
        results.status = "MARGINAL"
    else:
        results.status = "UNACCEPTABLE"

    return results

# ---------------------------------------------------------------------------
# Console Report (always printed)
# ---------------------------------------------------------------------------

def print_console_report(results: GRRResults, equipment: str, study_operator: str) -> None:
    """Print a formatted summary to stdout."""
    print()
    print("=" * 60)
    print("  GR&R STUDY RESULTS  —  AIAG MSA 4th Edition")
    print("=" * 60)
    print(f"  Equipment : {equipment}")
    print(f"  Performed : {study_operator}")
    print(f"  Date      : {date.today()}")
    print("-" * 60)
    print(f"  Grand Mean   : {results.grand_mean:.4f}")
    print(f"  R-bar-bar    : {results.r_bar_bar:.4f}")
    print(f"  X-diff       : {results.x_diff:.4f}")
    print(f"  Rp           : {results.rp:.4f}")
    print("-" * 60)
    print(f"  EV  (Repeatability)  : {results.ev:.4f}   ({results.pct_ev:.1f}%)")
    print(f"  AV  (Reproducibility): {results.av:.4f}   ({results.pct_av:.1f}%)")
    print(f"  GR&R                 : {results.grr:.4f}   ({results.pct_grr:.1f}%)")
    print(f"  PV  (Part Variation) : {results.pv:.4f}   ({results.pct_pv:.1f}%)")
    print(f"  TV  (Total Variation): {results.tv:.4f}")
    print(f"  ndc                  : {results.ndc:.1f}")
    print("-" * 60)
    print(f"  STATUS: {results.status}")
    print("=" * 60)
    print()

# ---------------------------------------------------------------------------
# PDF Report Generation
# ---------------------------------------------------------------------------

# Color palette — medical/industrial quality feel
COLOR_DARK_BLUE  = colors.HexColor("#1A3A5C")
COLOR_MID_BLUE   = colors.HexColor("#2E6DA4")
COLOR_LIGHT_GRAY = colors.HexColor("#F0F4F8")
COLOR_BORDER     = colors.HexColor("#C5D3E0")
COLOR_GREEN      = colors.HexColor("#2E7D32")
COLOR_AMBER      = colors.HexColor("#E65100")
COLOR_RED        = colors.HexColor("#B71C1C")
COLOR_WHITE      = colors.white
COLOR_BLACK      = colors.black


def _status_color(status: str) -> colors.Color:
    return {
        "ACCEPTABLE":   COLOR_GREEN,
        "MARGINAL":     COLOR_AMBER,
        "UNACCEPTABLE": COLOR_RED,
    }.get(status, COLOR_BLACK)


def _status_icon(status: str) -> str:
    return {
        "ACCEPTABLE":   "PASS",
        "MARGINAL":     "CAUTION",
        "UNACCEPTABLE": "FAIL",
    }.get(status, "")


def build_pdf_report(
    results:        GRRResults,
    output_path:    Path,
    equipment:      str,
    study_operator: str,
) -> None:
    """
    Generate a professional GR&R study PDF report using ReportLab Platypus.

    Layout:
        1. Title block with study metadata
        2. Horizontal rule
        3. Summary metrics table (all variation components + % + acceptance)
        4. Per-operator breakdown table
        5. Acceptance determination banner (color-coded)
        6. Interpretation notes
        7. Footer with regulatory citations

    Args:
        results:        Completed GRRResults from compute_grr().
        output_path:    Destination PDF file path.
        equipment:      Equipment / gage identifier string.
        study_operator: Name of QE who conducted the study.
    """
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=1.0 * inch,
        title="GR&R Study Report",
        author=study_operator,
        subject="Gauge Repeatability and Reproducibility — AIAG MSA 4th Ed.",
    )

    styles = getSampleStyleSheet()
    story  = []

    # ------------------------------------------------------------------
    # Helper styles
    # ------------------------------------------------------------------
    title_style = ParagraphStyle(
        "GRRTitle",
        parent=styles["Normal"],
        fontSize=18,
        leading=22,
        textColor=COLOR_DARK_BLUE,
        fontName="Helvetica-Bold",
    )
    subtitle_style = ParagraphStyle(
        "GRRSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=COLOR_MID_BLUE,
        fontName="Helvetica",
    )
    meta_style = ParagraphStyle(
        "GRRMeta",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        textColor=COLOR_BLACK,
        fontName="Helvetica",
    )
    section_hdr_style = ParagraphStyle(
        "GRRSection",
        parent=styles["Normal"],
        fontSize=11,
        leading=14,
        textColor=COLOR_DARK_BLUE,
        fontName="Helvetica-Bold",
        spaceAfter=4,
    )
    note_style = ParagraphStyle(
        "GRRNote",
        parent=styles["Normal"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#444444"),
        fontName="Helvetica",
    )
    footer_style = ParagraphStyle(
        "GRRFooter",
        parent=styles["Normal"],
        fontSize=7,
        leading=10,
        textColor=colors.HexColor("#666666"),
        fontName="Helvetica-Oblique",
    )

    # ------------------------------------------------------------------
    # Title Block
    # ------------------------------------------------------------------
    story.append(Paragraph("GR&amp;R Study Report", title_style))
    story.append(Paragraph(
        "Gauge Repeatability &amp; Reproducibility — AIAG MSA 4th Edition",
        subtitle_style,
    ))
    story.append(Spacer(1, 8))

    # Metadata table (2-column label / value)
    meta_data = [
        ["Equipment / Gage:", equipment],
        ["Study Performed By:", study_operator],
        ["Report Date:", str(date.today())],
        ["Study Design:", f"{len(results.operator_stats)} Operators, AIAG Crossed GR&R"],
        ["Regulatory Reference:", "21 CFR 820.72 | AIAG MSA 4th Ed."],
    ]
    meta_table = Table(meta_data, colWidths=[2.0 * inch, 5.25 * inch])
    meta_table.setStyle(TableStyle([
        ("FONTNAME",  (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",  (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE",  (0, 0), (-1, -1), 9),
        ("LEADING",   (0, 0), (-1, -1), 13),
        ("VALIGN",    (0, 0), (-1, -1), "TOP"),
        ("TEXTCOLOR", (0, 0), (0, -1), COLOR_DARK_BLUE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_MID_BLUE))
    story.append(Spacer(1, 12))

    # ------------------------------------------------------------------
    # Summary Metrics Table
    # ------------------------------------------------------------------
    story.append(Paragraph("Variation Components Summary", section_hdr_style))

    summary_header = ["Component", "Study Variation", "% of TV", "Threshold"]
    summary_rows = [
        ["EV — Equipment (Repeatability)",
         f"{results.ev:.4f}", f"{results.pct_ev:.1f}%", "—"],
        ["AV — Appraiser (Reproducibility)",
         f"{results.av:.4f}", f"{results.pct_av:.1f}%", "—"],
        ["GR&R — Combined",
         f"{results.grr:.4f}", f"{results.pct_grr:.1f}%",
         u"\u2264 10%: Accept | \u2264 30%: Marginal"],
        ["PV — Part Variation",
         f"{results.pv:.4f}", f"{results.pct_pv:.1f}%", "—"],
        ["TV — Total Variation",
         f"{results.tv:.4f}", "100.0%", "—"],
        ["ndc — Number of Distinct Categories",
         f"{results.ndc:.1f}", "—", u"\u2265 5 required"],
    ]

    summary_col_widths = [2.8 * inch, 1.3 * inch, 1.0 * inch, 2.15 * inch]
    summary_table = Table(
        [summary_header] + summary_rows,
        colWidths=summary_col_widths,
        repeatRows=1,
    )

    grr_row_idx = 3  # 1 header + 0-indexed row 2 = GR&R row
    ndc_row_idx = 6
    status_color = _status_color(results.status)

    summary_style = TableStyle([
        # Header
        ("BACKGROUND",   (0, 0), (-1, 0), COLOR_DARK_BLUE),
        ("TEXTCOLOR",    (0, 0), (-1, 0), COLOR_WHITE),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING",(0, 0), (-1, 0), 6),
        ("TOPPADDING",   (0, 0), (-1, 0), 6),
        # Body
        ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",     (0, 1), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLOR_WHITE, COLOR_LIGHT_GRAY]),
        ("BOTTOMPADDING",(0, 1), (-1, -1), 5),
        ("TOPPADDING",   (0, 1), (-1, -1), 5),
        ("ALIGN",        (1, 0), (-1, -1), "CENTER"),
        ("ALIGN",        (0, 0), (0, -1), "LEFT"),
        # GR&R row highlight
        ("TEXTCOLOR",    (0, grr_row_idx), (-1, grr_row_idx), status_color),
        ("FONTNAME",     (0, grr_row_idx), (-1, grr_row_idx), "Helvetica-Bold"),
        # ndc row highlight if below threshold
        *([("TEXTCOLOR", (0, ndc_row_idx), (1, ndc_row_idx), COLOR_RED),
           ("FONTNAME",  (0, ndc_row_idx), (1, ndc_row_idx), "Helvetica-Bold")]
          if results.ndc < NDC_MINIMUM else []),
        # Grid
        ("GRID",         (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ])
    summary_table.setStyle(summary_style)
    story.append(summary_table)
    story.append(Spacer(1, 14))

    # ------------------------------------------------------------------
    # Intermediate Values Table (traceability / audit trail)
    # ------------------------------------------------------------------
    story.append(Paragraph("Intermediate Calculation Values", section_hdr_style))

    intermed_data = [
        ["Parameter", "Symbol", "Value", "Formula"],
        ["Grand Mean",           "X-bar-bar",  f"{results.grand_mean:.4f}", "Mean of all measurements"],
        ["Avg Range (overall)",  "R-bar-bar",  f"{results.r_bar_bar:.4f}", "Mean of operator R-bars"],
        ["Operator Mean Spread", "X-diff",     f"{results.x_diff:.4f}",   "max(X-bar op) - min(X-bar op)"],
        ["Part Range",           "Rp",         f"{results.rp:.4f}",       "max(part avg) - min(part avg)"],
    ]
    intermed_table = Table(
        intermed_data,
        colWidths=[2.0 * inch, 1.1 * inch, 1.0 * inch, 3.15 * inch],
        repeatRows=1,
    )
    intermed_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), COLOR_MID_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), COLOR_WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [COLOR_WHITE, COLOR_LIGHT_GRAY]),
        ("GRID",          (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("ALIGN",         (2, 0), (2, -1), "CENTER"),
    ]))
    story.append(intermed_table)
    story.append(Spacer(1, 14))

    # ------------------------------------------------------------------
    # Per-Operator Breakdown Table
    # ------------------------------------------------------------------
    story.append(Paragraph("Per-Operator Breakdown", section_hdr_style))

    op_header = ["Operator", "Grand Mean (X-bar)", "Avg Range (R-bar)"]
    op_rows = [
        [op.name, f"{op.x_bar:.4f}", f"{op.r_bar:.4f}"]
        for op in results.operator_stats
    ]
    op_table = Table(
        [op_header] + op_rows,
        colWidths=[2.0 * inch, 2.25 * inch, 2.25 * inch],
        repeatRows=1,
    )
    op_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), COLOR_MID_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), COLOR_WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [COLOR_WHITE, COLOR_LIGHT_GRAY]),
        ("GRID",          (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("ALIGN",         (1, 0), (-1, -1), "CENTER"),
    ]))
    story.append(op_table)
    story.append(Spacer(1, 16))

    # ------------------------------------------------------------------
    # Acceptance Determination Banner
    # ------------------------------------------------------------------
    story.append(Paragraph("Acceptance Determination", section_hdr_style))

    icon  = _status_icon(results.status)
    color = _status_color(results.status)

    # Status box built as a single-cell table for background color control
    status_text = (
        f"<font name='Helvetica-Bold' size='14' color='white'>"
        f"[{icon}]  {results.status}"
        f"</font>"
        f"<br/>"
        f"<font name='Helvetica' size='10' color='white'>"
        f"  %GR&amp;R = {results.pct_grr:.1f}%  |  "
        f"ndc = {results.ndc:.1f}"
        f"</font>"
    )
    status_para = Paragraph(status_text, ParagraphStyle(
        "StatusBanner", alignment=1, leading=20,
    ))
    status_table = Table([[status_para]], colWidths=[7.25 * inch])
    status_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), color),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
        ("ROUNDEDCORNERS",(0, 0), (-1, -1), [4, 4, 4, 4]),
    ]))
    story.append(status_table)
    story.append(Spacer(1, 10))

    # ------------------------------------------------------------------
    # Interpretation Notes
    # ------------------------------------------------------------------
    interp_map = {
        "ACCEPTABLE": (
            "The measurement system is ACCEPTABLE per AIAG MSA 4th Edition criteria. "
            "%GR&R is at or below 10%, indicating the gage contributes minimal variation "
            "relative to total process variation. This instrument may be used for product "
            "acceptance decisions. Continue routine calibration per your control plan."
        ),
        "MARGINAL": (
            "The measurement system is MARGINAL. %GR&R falls between 10% and 30%. "
            "Use with caution — approval should be based on application importance, "
            "cost of gage improvement, and customer concurrence. Investigate dominant "
            "variation source (EV vs. AV) and consider operator re-training or gage upgrade."
        ),
        "UNACCEPTABLE": (
            "The measurement system is UNACCEPTABLE. %GR&R exceeds 30%. Do not use "
            "this gage for product acceptance. Identify and correct root cause before "
            "re-study. Common causes: gage discrimination, worn components, inconsistent "
            "measurement technique, environmental factors, or inadequate operator training."
        ),
    }
    ndc_note = (
        f"ndc = {results.ndc:.1f} — " + (
            "ADEQUATE: The gage can resolve 5 or more distinct categories of part variation. "
            if results.ndc >= NDC_MINIMUM
            else "INADEQUATE: ndc < 5. The gage cannot resolve enough part categories "
                 "for meaningful process control. Gage improvement is required."
        )
    )

    story.append(Paragraph(interp_map.get(results.status, ""), note_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph(ndc_note, note_style))
    story.append(Spacer(1, 14))

    # ------------------------------------------------------------------
    # AIAG Constants Reference (for audit traceability)
    # ------------------------------------------------------------------
    story.append(HRFlowable(width="100%", thickness=0.75, color=COLOR_BORDER))
    story.append(Spacer(1, 8))

    n_trials    = len(results.operator_stats[0].part_ranges) if results.operator_stats else 3
    n_operators = len(results.operator_stats)

    # Recover n_trials from first operator's part_ranges count
    const_text = (
        f"AIAG Constants Applied — "
        f"K1={K1_BY_TRIALS.get(n_trials, '?')} ({n_trials} trials), "
        f"K2={K2_BY_OPERATORS.get(n_operators, '?')} ({n_operators} operators), "
        f"K3 per part count. "
        f"Study variation = 5.15\u03c3 (99% of normal distribution)."
    )
    story.append(Paragraph(const_text, note_style))
    story.append(Spacer(1, 20))

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------
    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        "Reference: AIAG Measurement Systems Analysis Reference Manual, 4th Edition (2010). "
        "Regulatory basis: 21 CFR Part 820.72 — Inspection, Measuring, and Test Equipment "
        "(FDA Quality System Regulation). This report is a controlled quality record. "
        "Retain per applicable document control procedures.",
        footer_style,
    ))

    # ------------------------------------------------------------------
    # Build PDF
    # ------------------------------------------------------------------
    doc.build(story)
    print(f"[+] PDF report written to: {output_path}")

# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(
        prog="grr_tool.py",
        description=(
            "Gauge R&R Analysis Tool — AIAG MSA 4th Edition\n"
            "Generates a compliant GR&R study report for medical device quality engineering."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Generate sample data, then run analysis:\n"
            "  python grr_tool.py --generate-sample --input sample.csv "
            "--output report.pdf --equipment 'Caliper #3' --operator 'J. Smith'\n\n"
            "  # Analyze existing CSV:\n"
            "  python grr_tool.py --input my_data.csv --output grr_report.pdf "
            "--equipment 'Micrometer SN-0042' --operator 'QE Lab'\n"
        ),
    )
    p.add_argument(
        "--input", "-i",
        type=Path,
        required=True,
        metavar="CSV_FILE",
        help="Path to input CSV (columns: Part, Operator, Trial1, Trial2, Trial3)",
    )
    p.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("grr_report.pdf"),
        metavar="PDF_FILE",
        help="Path for output PDF report (default: grr_report.pdf)",
    )
    p.add_argument(
        "--equipment", "-e",
        type=str,
        default="Unspecified Gage",
        metavar="NAME",
        help="Equipment / gage identifier (e.g. 'Mitutoyo 293-340-30 SN-1234')",
    )
    p.add_argument(
        "--operator",
        type=str,
        default="Quality Engineering",
        metavar="NAME",
        help="Name of QE or team who performed the study",
    )
    p.add_argument(
        "--generate-sample",
        action="store_true",
        help="Generate a sample 10-part x 3-operator x 3-trial CSV before analysis",
    )
    return p.parse_args()


def main() -> None:
    """Main entry point — orchestrates sample generation, analysis, and reporting."""
    args = parse_args()

    # Optionally generate sample data
    if args.generate_sample:
        generate_sample_data(args.input)

    # Load and validate CSV
    records, n_parts, n_operators, n_trials = load_data(args.input)

    # Run AIAG GR&R calculations
    results = compute_grr(records, n_parts, n_operators, n_trials)

    # Console summary (always)
    print_console_report(results, args.equipment, args.operator)

    # PDF report
    build_pdf_report(results, args.output, args.equipment, args.operator)


if __name__ == "__main__":
    main()
