# GR&R Analysis Tool

Gauge Repeatability & Reproducibility (GR&R) analysis tool following the **AIAG MSA 4th Edition** standard.
Designed for medical device manufacturing quality engineering under **21 CFR 820.72** (FDA Inspection, Measuring, and Test Equipment).

---

## Overview

A GR&R study quantifies how much of the total process variation comes from the measurement system itself (gage + operators), versus actual part-to-part variation. This tool automates the full AIAG crossed GR&R calculation and produces a professional PDF report suitable for audit and regulatory records.

**Variation components computed:**

| Component | Symbol | Description |
|-----------|--------|-------------|
| Equipment Variation | EV | Repeatability — within-operator gage noise |
| Appraiser Variation | AV | Reproducibility — between-operator systematic offset |
| Combined GR&R | GR&R | √(EV² + AV²) |
| Part Variation | PV | True part-to-part variation |
| Total Variation | TV | √(GR&R² + PV²) |
| Distinct Categories | ndc | 1.41 × (PV / GR&R) |

**Acceptance criteria (AIAG MSA 4th Ed., Section III):**

| %GR&R | Verdict |
|-------|---------|
| ≤ 10% | ✅ Acceptable |
| 10–30% | ⚠️ Marginal |
| > 30% | ❌ Unacceptable |

ndc ≥ 5 is required for adequate measurement discrimination.

---

## Example Reports

Two contrasting studies are included to demonstrate the full range of outcomes.

### Example A — Mitutoyo 293-340-30 (MARGINAL)

> Dataset: [`sample_grr.csv`](sample_grr.csv) · Report: [`grr_report.pdf`](grr_report.pdf)

Precision digital micrometer with small operator biases (0 / +0.003 / −0.002 mm) and low gage noise (σ = 0.002 mm). Part spread ±0.030 mm around nominal 10.000 mm.

### Example B — Vernier Caliper VC-07 (UNACCEPTABLE)

> Dataset: [`sample_grr_marginal.csv`](sample_grr_marginal.csv) · Report: [`grr_report_marginal.pdf`](grr_report_marginal.pdf)

Worn vernier caliper with large operator biases (0 / +0.009 / −0.007 mm) and high gage noise (σ = 0.007 mm). Part spread ±0.012 mm around nominal 25.000 mm — tighter tolerance amplifies the measurement system's share of total variation.

### Side-by-side comparison

| Metric | Example A — Mitutoyo | Example B — Vernier Caliper |
|--------|----------------------|----------------------------|
| Equipment | Mitutoyo 293-340-30 SN-0042 | Vernier Caliper VC-07 SN-1138 |
| Nominal dimension | 10.000 mm | 25.000 mm |
| Gage noise (σ) | 0.002 mm | 0.007 mm |
| Max operator bias | ±0.003 mm | ±0.009 mm |
| EV — Repeatability | 0.0087 (10.1%) | 0.0381 (60.1%) |
| AV — Reproducibility | 0.0119 (13.7%) | 0.0424 (66.9%) |
| **%GR&R** | **17.0%** | **89.9%** |
| PV — Part Variation | 0.0854 (98.5%) | 0.0277 (43.7%) |
| TV — Total Variation | 0.0867 | 0.0634 |
| ndc | 8.2 ✅ | 0.7 ❌ |
| **Verdict** | ⚠️ **MARGINAL** | ❌ **UNACCEPTABLE** |

**Key takeaway:** Example B is unacceptable not because the gage is dramatically worse in absolute terms, but because the part spread is much tighter (±0.012 mm vs ±0.030 mm). When tolerances tighten, measurement system capability requirements become significantly stricter — the gage noise and operator variation now dominate total variation. Example A would move to ACCEPTABLE with operator re-training to reduce the reproducibility component.

---

## Files

| File | Description |
|------|-------------|
| `grr_tool.py` | Main analysis script (CLI) |
| `sample_grr.csv` | Example A dataset — Mitutoyo, 10 parts × 3 operators × 3 trials |
| `grr_report.pdf` | Example A PDF report — MARGINAL (17.0% GR&R) |
| `sample_grr_marginal.csv` | Example B dataset — Vernier Caliper, same study design |
| `grr_report_marginal.pdf` | Example B PDF report — UNACCEPTABLE (89.9% GR&R) |

---

## Requirements

```
pandas
reportlab
```

Install dependencies:

```bash
pip install pandas reportlab
```

---

## Usage

### Analyze an existing CSV

```bash
python grr_tool.py \
  --input sample_grr.csv \
  --output grr_report.pdf \
  --equipment "Mitutoyo 293-340-30 SN-1234" \
  --operator "QE Team"
```

### Generate sample data and analyze

```bash
python grr_tool.py \
  --generate-sample \
  --input sample_grr.csv \
  --output grr_report.pdf \
  --equipment "Digital Caliper #3" \
  --operator "J. Martinez"
```

### All options

```
--input,    -i  Path to input CSV (required)
--output,   -o  Path for output PDF report (default: grr_report.pdf)
--equipment,-e  Gage / equipment identifier string
--operator      Name of QE or team who performed the study
--generate-sample  Generate a synthetic 10×3×3 CSV before analysis
```

---

## Input CSV Format

Columns: `Part`, `Operator`, `Trial1`, `Trial2`, `Trial3` (2–5 trials supported)

```csv
Part,Operator,Trial1,Trial2,Trial3
P01,Alice,10.0089,10.0107,10.0097
P01,Bob,10.0116,10.0099,10.0094
...
```

Supported study dimensions:

| Dimension | Supported values |
|-----------|-----------------|
| Trials | 2, 3, 4, 5 |
| Operators | 2, 3, 4, 5 |
| Parts | 2–10 |

---

## Output

The tool prints a summary to stdout and generates a PDF report containing:

- Study metadata (equipment, operator, date)
- Variation components table with % of total variation
- Intermediate calculation values (R̄̄, X-diff, Rp) for audit traceability
- Per-operator breakdown (grand mean and average range)
- Color-coded acceptance determination banner (green / amber / red)
- Interpretation notes and corrective action guidance
- AIAG constants reference and regulatory footer

---

## Methodology

Implements the **AIAG crossed GR&R** method:

1. Compute per-operator average range (R̄) and grand mean (X̄)
2. R̄̄ = mean of operator R̄ values → source of EV
3. X-diff = max(operator X̄) − min(operator X̄) → source of AV
4. Apply AIAG K-constants (K1, K2, K3) derived from d2* control chart factors
5. AV corrected for finite sample size: AV = √(max(0, (X-diff·K2)² − EV²/(n·r)))
6. TV = √(GR&R² + PV²)
7. ndc = 1.41 × (PV / GR&R)

Study variation is expressed as **5.15σ** (99% of the normal distribution), per AIAG convention.

---

## Regulatory Reference

- AIAG *Measurement Systems Analysis Reference Manual*, 4th Edition (2010)
- 21 CFR Part 820.72 — Inspection, Measuring, and Test Equipment (FDA QSR)

Reports generated by this tool are quality records. Retain per applicable document control procedures.
