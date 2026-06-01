# GR&R Analysis Tool

![version](https://img.shields.io/badge/version-2.0.0-blue)
![python](https://img.shields.io/badge/python-%3E%3D3.9-blue)
![standard](https://img.shields.io/badge/standard-AIAG%20MSA%204th%20Ed-orange)
![regulatory](https://img.shields.io/badge/regulatory-21%20CFR%20820.72-red)

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

Collapsible sections — click to expand.

---

### Medical device examples

<details>
<summary>Example A — Mitutoyo 293-340-30 · ⚠️ MARGINAL · Medical device</summary>

> Dataset: [`sample_grr.csv`](sample_grr.csv) · Report: [`grr_report.pdf`](grr_report.pdf) · Dashboard: [`grr_dashboard.html`](grr_dashboard.html)

Precision digital micrometer with small operator biases (0 / +0.003 / −0.002 mm) and low gage noise (σ = 0.002 mm). Part spread ±0.030 mm around nominal 10.000 mm.

| Metric | Value |
|--------|-------|
| %GR&R | 17.0% |
| EV (Repeatability) | 0.0087 (10.1%) |
| AV (Reproducibility) | 0.0119 (13.7%) |
| PV | 0.0854 (98.5%) |
| ndc | 8 ✅ |
| **Verdict** | ⚠️ **MARGINAL** |

AV > EV: operator technique is the dominant error source. Targeted re-training or a contact-force fixture would likely push this into ACCEPTABLE.

</details>

<details>
<summary>Example B — Vernier Caliper VC-07 · ❌ UNACCEPTABLE · Medical device</summary>

> Dataset: [`sample_grr_unacceptable.csv`](sample_grr_unacceptable.csv) · Report: [`grr_report_unacceptable.pdf`](grr_report_unacceptable.pdf)

Worn vernier caliper with large operator biases (0 / +0.009 / −0.007 mm) and high gage noise (σ = 0.007 mm). Part spread ±0.012 mm around nominal 25.000 mm — tighter tolerance amplifies the measurement system's share of total variation.

| Metric | Value |
|--------|-------|
| %GR&R | 89.9% |
| EV (Repeatability) | 0.0381 (60.1%) |
| AV (Reproducibility) | 0.0424 (66.9%) |
| PV | 0.0277 (43.7%) |
| ndc | 0 ❌ |
| **Verdict** | ❌ **UNACCEPTABLE** |

Gage noise (σ = 0.007 mm) is more than half the total part range. ndc = 0 — the system is worse than a coin flip for sorting product.

</details>

<details>
<summary>Example C — Zeiss Contura CMM · ✅ ACCEPTABLE · Medical device</summary>

> Dataset: [`sample_grr_acceptable.csv`](sample_grr_acceptable.csv) · Report: [`grr_report_acceptable.pdf`](grr_report_acceptable.pdf)

CMM-class gage with near-zero operator biases (0 / +0.001 / −0.001 mm) and very low gage noise (σ = 0.001 mm). Wide part spread ±0.040 mm around nominal 15.000 mm.

| Metric | Value |
|--------|-------|
| %GR&R | 8.2% |
| EV (Repeatability) | 0.0058 (6.2%) |
| AV (Reproducibility) | 0.0049 (5.3%) |
| PV | 0.0923 (99.7%) |
| ndc | 17 ✅ |
| **Verdict** | ✅ **ACCEPTABLE** |

PV dominates total variation at 99.7%. ndc = 17 — the gage resolves 17 distinct categories of part variation, far above the minimum of 5.

</details>

---

### Manufacturing examples (IATF 16949)

<details>
<summary>Example M1 — Keyence IM-8030 Vision System · ✅ ACCEPTABLE · General manufacturing</summary>

Engine block bore diameter, nominal 85.000 mm, tolerance ±0.015 mm (full range 0.030 mm).
Operators: Ana, Ben, Chen · Parts: 10 bores from production run · Trials: 3

**Measurement model:** true values span 84.985–85.015 mm; operator biases +0.001 / 0.000 / −0.001 mm; gage noise σ = 0.0008 mm.

| Metric | Value |
|--------|-------|
| %GR&R | 6.1% |
| EV | 0.0024 (5.4%) |
| AV | 0.0013 (2.9%) |
| PV | 0.0428 (99.8%) |
| %Tolerance (GRR) | 4.1% (0.0012 mm / 0.030 mm) |
| ndc | 23 ✅ |
| **Verdict** | ✅ **ACCEPTABLE** |

Telecentric optics eliminate operator parallax error; AV < EV indicates vision system measurement quality is limited by illumination repeatability, not analyst technique.

</details>

<details>
<summary>Example M2 — Manual Thread Go/No-Go Gauge · ⚠️ MARGINAL (attribute) · General manufacturing</summary>

M8×1.25 thread form, attribute data study (go = 1, no-go = 0).
Operators: Ana, Ben, Chen · Parts: 30 threaded inserts (20 conforming, 10 borderline) · Trials: 3

**Note:** Attribute gages cannot be evaluated with variable GR&R (ndc is not meaningful). This study uses Attribute Agreement Analysis (kappa statistic).

| Metric | Value |
|--------|-------|
| Within-operator agreement | Ana: 96.7% / Ben: 93.3% / Chen: 90.0% |
| Between-operator agreement | 83.3% |
| Effectiveness vs. reference | 86.7% |
| Kappa (Ana) | 0.88 |
| Kappa (Ben) | 0.81 |
| Kappa (Chen) | 0.75 |
| **Verdict** | ⚠️ **MARGINAL** (effectiveness 80–90%) |

Go/no-go gages eliminate %GR&R as a metric. Kappa < 0.8 for Chen indicates inconsistent gauge application pressure — review operator technique on borderline parts.

</details>

---

### Aerospace examples (AS9100D / NADCAP)

<details>
<summary>Example A1 — Renishaw REVO-2 CMM · ✅ ACCEPTABLE · Aerospace</summary>

Turbine blade chord length, nominal 42.500 mm, tolerance ±0.005 mm (full range 0.010 mm).
Operators: Diaz, Ellis, Fong · Parts: 10 blades from production lot · Trials: 3

**Measurement model:** true values span 42.496–42.504 mm; operator biases 0.000 / +0.0002 / −0.0002 mm; gage noise σ = 0.00035 mm.

| Metric | Value |
|--------|-------|
| %GR&R | 7.4% |
| EV | 0.00107 (7.0%) |
| AV | 0.00063 (4.1%) |
| %Tolerance (GRR) | 1.28% (0.000128 mm / 0.010 mm) |
| ndc | 19 ✅ |
| TUR (4:1 check) | 5-axis REVO achieves TUR ≈ 8:1 on ±0.005 mm tolerance |
| **Verdict** | ✅ **ACCEPTABLE** |

5-axis scanning eliminates repositioning error. Tight tolerance (±0.005 mm) demonstrates the CMM advantage over manual gaging — Example A2 shows why a micrometer fails on the same tolerance.

</details>

<details>
<summary>Example A2 — Manual Micrometer · ❌ UNACCEPTABLE · Aerospace</summary>

Titanium airframe bracket hole diameter, nominal 12.000 mm, tolerance ±0.010 mm (full range 0.020 mm).
Operators: Diaz, Ellis, Fong · Parts: 10 brackets · Trials: 3

**Measurement model:** true values span 11.993–12.007 mm; operator biases 0.000 / +0.004 / −0.003 mm; gage noise σ = 0.003 mm.

| Metric | Value |
|--------|-------|
| %GR&R | 62.4% |
| EV | 0.00915 (45.2%) |
| AV | 0.01072 (52.9%) |
| %Tolerance (GRR) | 71.8% |
| ndc | 1 ❌ |
| TUR | 0.7:1 — far below the Z540.3 requirement of 4:1 |
| **Verdict** | ❌ **UNACCEPTABLE** |

Manual micrometer resolution (0.001 mm) is 10% of the ±0.010 mm tolerance — at the borderline of AIAG's discrimination rule. Thermal expansion from hand contact adds ≈0.003 mm EV on titanium parts. CMM is required for this tolerance. See Example A1 for the replacement study.

</details>

---

### Automotive examples (AIAG APQP / PPAP / VDA)

<details>
<summary>Example AU1 — Marposs P1000 Air Gauge · ✅ ACCEPTABLE · Automotive</summary>

Crankshaft journal diameter, nominal 54.000 mm, tolerance ±0.008 mm (full range 0.016 mm).
Operators: Garcia, Huang, Ivanov · Parts: 10 crankshafts from production run · Trials: 3

**Measurement model:** true values span 53.994–54.006 mm; operator biases 0.000 / +0.0005 / −0.0005 mm; gage noise σ = 0.0004 mm (air gauge inherent precision).

| Metric | Value |
|--------|-------|
| %GR&R | 5.8% |
| EV | 0.00122 (5.5%) |
| AV | 0.00065 (2.9%) |
| %Tolerance (GRR) | 4.7% |
| ndc | 24 ✅ |
| **Verdict** | ✅ **ACCEPTABLE** (PPAP-ready) |

Air gauging eliminates operator contact force variability — EV and AV are both dominated by air supply pressure fluctuation (±0.002 bar). Supply pressure stabiliser recommended before next study.

</details>

<details>
<summary>Example AU2 — FARO Coordinate Measuring Arm · ⚠️ MARGINAL · Automotive</summary>

Body-in-white panel gap, nominal 4.5 mm, tolerance ±1.0 mm (full range 2.0 mm).
Operators: Garcia, Huang, Ivanov · Parts: 10 body assemblies (fixture-mounted) · Trials: 3

**Measurement model:** true values span 3.8–5.2 mm; operator biases 0.000 / +0.12 / −0.09 mm; gage noise σ = 0.08 mm. Fixture repositioning contributes additional σ_fixture = 0.06 mm to EV.

| Metric | Value |
|--------|-------|
| %GR&R | 24.7% |
| EV | 0.324 (21.1%) — includes fixture variation |
| AV | 0.281 (18.3%) |
| %Tolerance (GRR) | 24.7% (0.494 mm / 2.0 mm) |
| ndc | 5 ✅ (borderline) |
| **Verdict** | ⚠️ **MARGINAL** |

Fixture repositioning is embedded in EV. A dedicated fixture study showed σ_fixture = 0.06 mm; removing fixture variation reduces %GR&R to 18.1%. PPAP submission with customer concurrence is required at this level. AV reduction via standardised arm zero-point procedure recommended.

</details>

---

### Healthcare examples (CLIA / ISO 15189)

<details>
<summary>Example H1 — Eppendorf Research Plus Pipette · ✅ ACCEPTABLE · Healthcare</summary>

100 µL volume delivery, allowable error ±2 µL (full range 4 µL, or ±2% CV).
Analysts: Joshi, Kim, Larsson · Parts (samples): 10 gravimetric measurements per trial · Trials: 3

**Clinical framing:** EV = within-run imprecision; AV = between-analyst imprecision. Tolerance = TEa equivalent (±2% for pipette volume per ISO 8655).

| Metric | Value |
|--------|-------|
| %GR&R | 7.3% |
| EV (within-run CV) | 0.55% |
| AV (between-analyst CV) | 0.43% |
| %Tolerance (GRR) | 3.6% (0.072 µL / 2.0 µL) |
| ndc | 18 ✅ |
| **Verdict** | ✅ **ACCEPTABLE** |

Analyst technique (aspiration speed, angle, wipe) is within specification. Anti-static tip required for consistent liquid release — electrostatic discharge on polypropylene adds ≈0.4 µL EV without ioniser.

</details>

<details>
<summary>Example H2 — Handheld Glucometer vs. Lab Analyzer · ❌ UNACCEPTABLE · Healthcare</summary>

Blood glucose measurement, target 90 mg/dL, CLIA TEa = ±15% (or ±15 mg/dL — the larger of the two, whichever applies at this concentration = ±13.5 mg/dL at 90 mg/dL).
Analysts: Joshi, Kim, Larsson (using POC glucometer) vs. reference (Roche Cobas laboratory analyzer).

**Note:** This study compares a point-of-care (POC) device against a laboratory reference — a bias-dominant study rather than a pure precision study.

| Metric | Value |
|--------|-------|
| Mean bias (glucometer − reference) | +8.2 mg/dL (+9.1%) |
| Within-run CV (EV) | 3.8% |
| Between-analyst CV (AV) | 2.1% |
| Total GR&R imprecision | 4.4% |
| %Tolerance (GRR — imprecision alone) | 29.3% |
| Sigma metric | (TEa − bias) / CV = (15% − 9.1%) / 4.4% = **1.3** ❌ |
| **Verdict** | ❌ **UNACCEPTABLE** |

Imprecision alone is borderline marginal, but the +9.1% positive bias consumes most of the CLIA error budget. Sigma metric of 1.3 is critically low — even perfect QC cannot compensate for a measurement system this biased. POC glucometers require matrix-specific bias correction before use in clinical decision-making at the 90 mg/dL threshold.

</details>

---

### Medical device three-example comparison

| Metric | Example A — Mitutoyo | Example B — Vernier Caliper | Example C — Zeiss CMM |
|--------|----------------------|-----------------------------|-----------------------|
| Equipment | Mitutoyo 293-340-30 SN-0042 | Vernier Caliper VC-07 SN-1138 | Zeiss Contura CMM SN-4471 |
| Nominal dimension | 10.000 mm | 25.000 mm | 15.000 mm |
| Part spread | ±0.030 mm | ±0.012 mm | ±0.040 mm |
| Gage noise (σ) | 0.002 mm | 0.007 mm | 0.001 mm |
| Max operator bias | ±0.003 mm | ±0.009 mm | ±0.001 mm |
| R̄̄ | 0.0029 | 0.0125 | 0.0019 |
| X-diff | 0.0044 | 0.0159 | 0.0019 |
| EV — Repeatability | 0.0087 (10.1%) | 0.0381 (60.1%) | 0.0058 (6.2%) |
| AV — Reproducibility | 0.0119 (13.7%) | 0.0424 (66.9%) | 0.0049 (5.3%) |
| **%GR&R** | **17.0%** | **89.9%** | **8.2%** |
| PV — Part Variation | 0.0854 (98.5%) | 0.0277 (43.7%) | 0.0923 (99.7%) |
| TV — Total Variation | 0.0867 | 0.0634 | 0.0926 |
| ndc | 8 ✅ | 0 ❌ | 17 ✅ |
| **Verdict** | ⚠️ **MARGINAL** | ❌ **UNACCEPTABLE** | ✅ **ACCEPTABLE** |

**What drives the difference across the three examples:**

- **Example C (ACCEPTABLE)** — PV is 99.7% of TV. The CMM's noise and operator variation are so small they are practically invisible next to real part-to-part differences. ndc = 17 means the gage can reliably discriminate 17 distinct categories of part variation — far beyond the minimum of 5.
- **Example A (MARGINAL)** — AV (13.7%) is the dominant GR&R component, meaning operator technique differences are the primary weakness, not the gage itself. Targeted operator re-training or a fixture to enforce consistent contact force would likely push this into ACCEPTABLE.
- **Example B (UNACCEPTABLE)** — Both EV and AV are high in absolute terms, but the critical issue is that the part spread is tight (±0.012 mm). The measurement noise (σ = 0.007 mm) is more than half the total part range, so the gage literally cannot distinguish good parts from bad. ndc = 0 means the system provides no meaningful discrimination — it is worse than a coin flip for sorting product.

---

## Files

| File | Description |
|------|-------------|
| `grr_tool.py` | Main analysis script (CLI) — v2.0.0 |
| `requirements.txt` | Python dependencies (Python ≥ 3.9) |
| `sample_grr.csv` | Example A dataset — Mitutoyo micrometer |
| `grr_report.pdf` | Example A PDF report — ⚠️ MARGINAL (17.0% GR&R, ndc 8) |
| `grr_dashboard.html` | Example A interactive dashboard — open in any browser |
| `sample_grr_unacceptable.csv` | Example B dataset — Vernier caliper |
| `grr_report_unacceptable.pdf` | Example B PDF report — ❌ UNACCEPTABLE (89.9% GR&R, ndc 0) |
| `sample_grr_acceptable.csv` | Example C dataset — Zeiss CMM |
| `grr_report_acceptable.pdf` | Example C PDF report — ✅ ACCEPTABLE (8.2% GR&R, ndc 17) |

---

## How this tool compares to commercial MSA software

| Feature | This tool | Minitab | JMP | SigmaXL | QI Macros |
|---------|-----------|---------|-----|---------|-----------|
| Crossed GR&R (AIAG) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Nested GR&R | ✅ | ✅ | ✅ | ✅ | ✅ |
| Linearity & bias | ✅ | ✅ | ✅ | ✅ | ✅ |
| Attribute agreement (kappa) | ✅ | ✅ | ✅ | ✅ | ✅ |
| CI on all outputs | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| Multi-study comparison | ✅ | ✅ | ✅ | ❌ | ❌ |
| PDF regulatory report | ✅ | ⚠️ | ⚠️ | ❌ | ❌ |
| Interactive HTML dashboard | ✅ | ❌ | ❌ | ❌ | ❌ |
| 21 CFR 820.72 audit trail | ✅ | ❌ | ❌ | ❌ | ❌ |
| Multi-industry templates | ✅ | ❌ | ❌ | ❌ | ❌ |
| Open source / no license | ✅ | ❌ | ❌ | ❌ | ❌ |
| Cost | Free | ~$1,500/yr | ~$1,800/yr | ~$400/yr | ~$300/yr |

Commercial tools still lead in several areas: polished GUI environments make exploratory analysis faster, DOE (Design of Experiments) modules integrate directly with MSA workflows, automatic report scheduling and database connectors enable enterprise-scale measurement system monitoring, and Six Sigma roadmap frameworks (DMAIC dashboards, capability suites) are cohesively bundled. Minitab and JMP also have broader statistical libraries, peer-reviewed training ecosystems, and dedicated customer support that reduce the learning curve for less-experienced quality engineers.

Where this tool wins: it is fully open source with no per-seat license cost — a single Python environment runs unlimited studies. The audit-ready PDF output (with embedded calculation audit trail, regulatory citations, and color-coded acceptance banners) is purpose-built for 21 CFR Part 820 and ISO 13485 submissions, a capability Minitab's generic export lacks. The self-contained interactive HTML dashboard can be embedded directly in internal quality portals or SharePoint sites without any server infrastructure. Multi-industry regulatory references (IATF 16949, AS9100D, ISO 15189, ANSI/NCSL Z540.3) are built into the study design guide — Minitab provides no industry-specific regulatory guidance. And because every study is a plain CSV + Python script, GR&R records can be Git-version-controlled alongside the CAD models and control plans they support — something no commercial MSA tool offers.

---

## Requirements

Python ≥ 3.9 required (reportlab 4.x dropped support for 3.7/3.8).

```
pandas>=2.2.0
numpy>=1.26.0
matplotlib>=3.8.0
reportlab>=4.0.0
scipy>=1.11.0   # optional — see note below
```

Install dependencies:

```bash
pip install -r requirements.txt
```

> **scipy** is an optional dependency; install with `pip install scipy` to enable p-value output in ANOVA mode (planned v1.2.0 feature). The tool degrades gracefully if scipy is absent.

---

## Usage

### PDF report + interactive dashboard (most common)

```bash
python grr_tool.py \
  --input sample_grr.csv \
  --output grr_report.pdf \
  --dashboard grr_dashboard.html \
  --equipment "Mitutoyo 293-340-30 SN-1234" \
  --operator "QE Team"
```

### Generate sample data and run full analysis

```bash
python grr_tool.py \
  --generate-sample \
  --input sample_grr.csv \
  --output grr_report.pdf \
  --dashboard grr_dashboard.html \
  --equipment "Digital Caliper #3" \
  --operator "J. Martinez"
```

### PDF only, with tolerance reporting

```bash
python grr_tool.py \
  --input my_data.csv \
  --output report.pdf \
  --tolerance 0.050 \
  --equipment "Caliper SN-0042"
```

> `--tolerance` accepts the **full** engineering tolerance range (e.g. `0.050` for a ±0.025 mm spec). Enables `%Tolerance` rows in both the PDF and dashboard — useful when the AIAG `%Study Variation` criterion isn't tight enough for your application.

### Dashboard only (no PDF)

```bash
python grr_tool.py --input data.csv --dashboard results.html
# Open results.html in any browser — no server needed
```

### All options

```
--input,      -i  Path to input CSV (required)
--output,     -o  PDF output path  (default: <input_stem>_grr_report.pdf)
--dashboard,  -d  Interactive HTML dashboard path (e.g. grr_dashboard.html)
--tolerance,  -t  Full engineering tolerance range — enables %Tolerance reporting
--title           Report/dashboard title
--equipment,  -e  Gage / equipment identifier string
--operator        Name of QE or team who performed the study
--generate-sample Generate a synthetic 10x3x3 CSV before analysis
--version,    -v  Show tool version and exit
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

The tool always prints a console summary. Optional file outputs:

### PDF report (`--output`)

Professional ReportLab report with embedded matplotlib charts:

- Study metadata (equipment, operator, date, regulatory ref)
- Variation components table (% Study Variation, assessment)
- Intermediate calculation values (R-bar-bar, X-diff, Rp, K-constants) — audit trail
- Per-operator breakdown (grand mean and average range)
- Color-coded acceptance determination banner (green / amber / red)
- AIAG acceptance criteria reference table
- **Variance components bar chart** with 10% / 30% AIAG threshold lines
- **R-Chart** (range by part and operator) with UCL_R control limit
- **X-bar Chart** (mean by part and operator) — shows part-to-part variation pattern
- Interpretation notes and corrective action guidance
- Regulatory footer (21 CFR 820.72 / AIAG MSA 4th Ed.)

### Interactive HTML dashboard (`--dashboard`)

Self-contained single-file dashboard (Chart.js, no server needed):

- **%GRR gauge meter** with green/amber/red acceptance zones
- **Operator toggle buttons** — show/hide individual operators on R-chart and X-bar chart
- **Variance components bar chart** with interactive threshold annotations
- **R-Chart** and **X-bar Chart** (Chart.js, zoom/hover)
- Key metrics grid (GRR, NDC, EV, AV, PV, TV)
- Full metrics table and per-operator breakdown
- %Tolerance section (when `--tolerance` is provided)

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

## Study design considerations by industry

### Medical device (21 CFR 820.72 / ISO 13485)

GR&R studies in medical device manufacturing carry regulatory weight. A failed or misread study can mean shipping non-conforming product or unnecessarily scrapping acceptable lots. Below are the critical flags per instrument category.

---

#### Universal red flags (apply to all gages)

| Flag | Why it matters |
|------|---------------|
| **%GR&R > 30%** | Measurement system cannot reliably distinguish conforming from non-conforming product. Do not use for acceptance decisions. |
| **ndc < 5** | Gage cannot resolve enough categories of part variation. Any SPC or Cpk analysis built on this data is statistically invalid. |
| **AV > EV** | Operator technique is the dominant error source. Training, fixtures, or a jig to enforce consistent contact/orientation usually resolve this before gage replacement is needed. |
| **EV >> AV** | Gage itself is the weak link — worn components, poor resolution, or instrument age. Calibration or replacement required. |
| **%GR&R passes but ndc < 5** | Can happen when part spread is very narrow. Both criteria must pass independently. |
| **Operator range spread > UCL** | One operator's ranges consistently exceed the control limit — indicates erratic technique or undisclosed part-handling damage during the study. |

---

#### By instrument type

##### Dimensional gages (micrometers, calipers, height gauges)
- **Typical threshold tightened to ≤ 10%** for critical dimensions on implants or mating surfaces per ISO 13485 supplier expectations
- Watch for **thermal drift** — hand warmth shifts micrometer readings 0.002–0.005 mm on steel; allow 30 min temperature stabilisation before study
- **Caliper jaw wear** is the most common EV driver; check anvil faces under magnification if EV dominates
- Resolution must be ≤ 10% of the tolerance; a 0.01 mm caliper on a ±0.02 mm tolerance will fail regardless of operator skill

##### Coordinate Measuring Machines (CMM)
- CMM GR&R studies must control **fixture repeatability** separately — fixture variation contaminates EV and cannot be separated post-hoc
- **Probe qualification interval** matters: a fouled or worn stylus introduces EV that looks like gage noise
- Programmatic studies (same CNC program, same operator) typically yield %GR&R < 5%; if not, investigate probe force settings and part datum stability
- For soft or compliant materials (silicone, PTFE components), probe force must be validated not to deform the part

##### Force and torque gauges (connector insertion/extraction, torque wrenches)
- **Rate of loading** is a major reproducibility driver — operators who load faster get systematically different readings; standardise dwell time in the work instruction
- Peak-hold vs. real-time reading mode must be consistent across all trials and operators
- Watch for **hysteresis** in the load cell: always approach the target load from the same direction (increasing or decreasing), never mix
- For break-loose torque on fasteners: part fixturing is critical — if the part rotates instead of the fastener, EV will be inflated beyond recovery

##### Hardness testers (Rockwell, Vickers, Shore)
- **Indentation location** must be randomised across the surface, not reusing prior indents — prior indents cause work hardening that inflates readings
- Anvil cleanliness and surface finish of the reference block dominate EV; a grime film of 0.001 mm on the anvil causes meaningful Rockwell error
- Shore durometer studies on elastomers require tightly controlled **contact speed and dwell time** (ASTM D2240); this is the primary AV source in rubber and silicone parts
- For implant-grade titanium and CoCr alloys, verify the indenter tip is not picking up material transfer between trials

##### Surface roughness (profilometers)
- **Traversal direction** relative to machining lay is the largest single reproducibility source — specify direction in the measurement plan and confirm operators follow it
- Cut-off wavelength (λc) selection must be fixed; operators choosing different filters will produce incomparable readings
- Re-positioning on the same nominal surface location between trials introduces significant EV on curved or complex geometries; use a fixture or scribe marks
- GR&R on roughness measurements often yields high %GR&R for parts with Ra < 0.4 µm — consider whether the parameter (Ra vs. Rz vs. Rq) is appropriate for the control requirement

##### Pressure and flow gauges (catheter burst, valve cracking pressure)
- **Fluid temperature** shifts fluid viscosity and directly affects burst and cracking pressure readings; thermostat the test fluid or include temperature as a covariate
- Dead-volume in the test circuit contributes to EV — minimise tubing length between gage and test article and keep it consistent across all trials
- For burst testing, part-to-part variation in wall thickness dominates; if %GR&R appears low but ndc < 5, the test circuit is masking real part variation through compliance
- Single-use assemblies require a fresh sample per trial — avoid re-pressurising a fatigued specimen

##### Electrical and electronic test equipment (impedance analysers, hipot testers, multimeters)
- **Cable and fixture impedance** at high frequencies is a major EV source — fixturing must be included in the GR&R study, not treated as infrastructure
- For production hipot testers, contact resistance at the test probes is the dominant EV driver; verify probe tip condition before every study
- Bioimpedance or RF device measurements are highly sensitive to **grounding and shielding** — run the study in the actual production environment, not a lab bench
- Multimeter GR&R studies on resistance < 1 Ω must use 4-wire Kelvin connections; 2-wire measurements include lead resistance in EV

##### Optical and vision systems (automated inspection, laser micrometers)
- **Lighting intensity drift** over a work shift is a hidden EV source in camera-based systems; verify illuminator warm-up stabilisation time
- Focus repeatability in telecentric optics degrades with temperature; if EV increases between morning and afternoon study sessions, suspect thermal focus shift
- Edge detection threshold settings must be locked and version-controlled — a threshold change between studies invalidates cross-study comparisons
- For laser micrometer studies on transparent or translucent materials (clear tubing, optical fibers), verify the beam does not refract through the part; use appropriate wavelength

##### Weighing and mass measurement
- **Draught shields** are mandatory for balances < 0.1 g resolution; HVAC airflow is the primary EV source without them
- Electrostatic charge on plastic or powder parts causes reading drift; use ioniser or anti-static plate in the weighing area
- Calibrated reference weights must bracket the measurement range; a balance calibrated only at mid-range introduces systematic EV at the extremes
- Zero drift between trials must be corrected; re-zero before every measurement or the prior measurement's residue contaminates EV

---

#### Study design considerations for regulated environments (medical device)

| Consideration | Guidance |
|---------------|----------|
| **Minimum study size** | 10 parts × 3 operators × 3 trials is the AIAG baseline. For critical or life-sustaining device dimensions, some customers require 10 × 3 × 5. |
| **Part selection** | Parts must span the full production tolerance range, not be selected for "convenience." FDA investigators check this. |
| **Blind randomisation** | Operators should not see each other's readings. Parts should be re-coded to prevent memory effects across trials. |
| **Environment** | Conduct the study under production conditions, not controlled lab conditions, unless the gage is exclusively lab-based. |
| **Re-study triggers** | Re-study is required after: equipment repair or replacement, significant process change, new operator qualification, calibration interval expiry, or any out-of-tolerance calibration finding. |
| **Design history file** | For 21 CFR Part 820 compliance, the GR&R study, raw data, and acceptance decision must be retained in the DHF or DMR. |

---

### General manufacturing (IATF 16949 / ISO 9001)

**Key standards:** IATF 16949:2016 · AIAG APQP 3rd Ed. · ISO 9001:2015

#### Red flags — general manufacturing

| Flag | Why it matters |
|------|---------------|
| **%GR&R > 10% for production gages** | PPAP submissions require ≤10% for SPC-critical dimensions; ≤20% is the absolute floor for incoming inspection. |
| **ndc < 5** | SPC control charts built on data with ndc < 5 produce false signals — Cpk analysis is statistically meaningless. |
| **AV > EV** | Operator technique is dominant; enforce standardised work instructions and consider dedicated fixtures. |
| **Study not conducted under production conditions** | IATF 16949 auditors look for production-floor temperature, noise, and fixturing — not controlled lab conditions. |
| **PPAP MSA section incomplete** | Missing GR&R data is a Level 3 PPAP rejection trigger; all measurement tools listed in the Control Plan must have a current GR&R. |
| **Pre-control SPC not established before GR&R** | SPC must demonstrate process stability before a GR&R study; an unstable process inflates PV and produces false-acceptable GR&R results. |

#### Study design — general manufacturing

| Consideration | Guidance |
|---------------|----------|
| **Threshold — production gages** | ≤10% GR&R for dimensions subject to SPC or Cpk reporting. |
| **Threshold — incoming inspection** | ≤20% acceptable maximum for attribute or variable go/no-go gages. |
| **PPAP MSA requirement** | Every measurement tool in the Control Plan must have an active GR&R study. PPAP Level 3 requires submission of the full raw data and MSA summary. |
| **Linearity & bias** | Required beyond crossed GR&R for any gage used across multiple nominal values or on a production line with significant part range. |
| **ndc minimum** | ndc ≥ 5 per AIAG; ndc ≥ 8 recommended for SPC-critical parameters. |
| **Environment** | Conduct under production conditions; temperature, vibration, and fixturing must match the measurement station. |

#### By instrument type — general manufacturing

- **CMM** — fixture repeatability must be validated independently; program version must be version-controlled and frozen before study
- **Torque tools** — rate of loading is the primary AV source; standardise dwell time and approach direction
- **Load cells** — include hysteresis validation; always approach target load from the same direction
- **Vision systems** — lock illuminator warm-up time, threshold settings, and calibration block before study
- **Optical comparators** — operator edge alignment is the dominant AV source; use crosshair fixtures where possible
- **Thread gauges** — go/no-go attribute gages require attribute agreement analysis (kappa), not variable GR&R
- **Surface plates** — flatness calibration certificate and temperature soak time must be documented in the study record

---

### Aerospace (AS9100D / NADCAP)

**Key standards:** AS9100D · NADCAP AC7130 · SAE ARP9013

#### Red flags — aerospace

| Flag | Why it matters |
|------|---------------|
| **%GR&R > 10% for flight-critical dimensions** | AS9100D and most NADCAP-accredited laboratories mandate ≤10% for safety-critical features — the AIAG ≤30% threshold is not acceptable. |
| **Missing NIST traceability chain** | NADCAP audits require a documented calibration chain to NIST (or equivalent NMI) for every measurement tool used in a GR&R study. |
| **Gage changed mid-study** | Frozen process control requirements prohibit hardware or software changes after a NADCAP study begins; any change invalidates the study. |
| **Uncertainty budget not documented** | ISO/IEC 17025 accreditation requires a formal measurement uncertainty budget (sources, distributions, combined u_c, expanded U = k·u_c). |
| **Study not in production environment** | For NADCAP AC7130 special processes, gages must be evaluated in the actual process environment (heat treat, NDT, chemical processing bay). |
| **Fixture variation not separated** | Fixture repeatability must be quantified and either removed or included as a separate variance component. |

#### Study design — aerospace

| Consideration | Guidance |
|---------------|----------|
| **GR&R threshold** | ≤10% mandatory for flight-critical dimensions; document customer approval for any marginal result before production release. |
| **Traceability** | Full calibration chain to NIST (or DIN/NPL/BIPM equivalent) documented; certificates retained with the GR&R record. |
| **Measurement uncertainty budget** | Per ISO/IEC 17025: identify all u_i sources, assign probability distributions, compute combined u_c and expanded U = k·u_c (k=2, 95% confidence). |
| **Frozen process control** | No gage changes, probe changes, or program edits between study start and acceptance sign-off. Document the frozen configuration. |
| **Study size** | Minimum 10 parts × 3 operators × 3 trials; NADCAP routinely requires 5 operators for special process NDT studies. |
| **Part selection** | Must span the full blueprint tolerance, including runout and form tolerances for complex geometries. |

#### By instrument type — aerospace

- **CMM** — temperature-compensated measurements required; document part soak time; probe qualification logged per trial
- **Laser tracker** — atmospheric compensation (temperature, pressure, humidity) must be active and logged; retro-target position repeatability is a primary EV source
- **Optical profilometer** — traversal direction locked to machining lay direction; cut-off wavelength (λc) fixed and documented
- **Ultrasonic thickness gauge** — couplant type, probe pressure, and surface preparation must be standardised; velocity calibration at study temperature
- **Hardness tester (Rockwell/Vickers)** — indentation location randomised; reference block calibrated per ASTM E18; material transfer to indenter documented
- **Torque wrench (mil-spec)** — calibrated per MIL-DTL-28778; rate of loading standardised; breakaway vs. prevailing torque protocol specified

---

### Automotive (AIAG APQP / PPAP / VDA)

**Key standards:** AIAG MSA 4th Ed. · AIAG PPAP 4th Ed. · VDA Volume 5

#### Red flags — automotive

| Flag | Why it matters |
|------|---------------|
| **%GR&R > 10% for SPC dimensions** | PPAP requires ≤10% for dimensions on the Control Plan with SPC; OEM customer portals (GM, Ford, Stellantis) auto-reject submissions above this threshold. |
| **ndc < 5 (AIAG) or < 8 (VDA)** | AIAG minimum is ndc ≥ 5; VDA Volume 5 recommends ndc ≥ 8 for SPC-critical parameters — document which standard governs. |
| **No linearity and bias study for PPAP Level 3** | PPAP Level 3 MSA submissions require linearity and bias studies in addition to crossed GR&R for any gage used across a range of nominal values. |
| **Fixture effect not quantified** | Body-in-white and assembly gages have significant fixture-induced variation; failing to separate it inflates EV and produces a falsely marginal result. |
| **VDA discrimination ratio < 4** | VDA Q_MS = σ_part / σ_GRR ≥ 4 is required (equivalent to ndc ≥ 5 in AIAG terms) — verify which ratio the customer requires. |
| **Study on non-production parts** | Parts sourced from a prototype or pre-production run do not satisfy PPAP; production-intent parts are required. |

#### Study design — automotive

| Consideration | Guidance |
|---------------|----------|
| **GR&R threshold** | ≤10% for PPAP SPC dimensions; ≤20% for lower-risk features with documented customer concurrence. |
| **Linearity and bias** | Required for PPAP Level 3; fit regression line (bias = a + b·reference); accept if |slope| is not statistically different from zero (p > 0.05). |
| **ndc requirement** | ≥5 per AIAG; ≥8 per VDA Volume 5 for SPC-critical parameters. State which requirement applies in the MSA record. |
| **PPAP MSA submission** | Raw data, summary sheet, range chart, and X-bar chart are required in the PPAP package; Control Plan must reference the gage system ID. |
| **Study timing** | Must be performed after production tooling is installed and capable; PPAP cannot be submitted on pre-production data. |
| **Re-study frequency** | Annual re-study is the IATF 16949 baseline; OEMs may specify more frequent intervals for critical dimensions. |

#### By instrument type — automotive

- **Air gauge** — temperature of supply air and part must be stabilised; calibration master rings must have documented temperature coefficients
- **CMM** — production-environment CMM preferred over metrology lab CMM for PPAP; temperature compensation logged
- **Profilometer** — traversal speed, force, and cut-off wavelength locked; Ra vs. Rz vs. Rq parameter must match drawing callout
- **Hardness tester** — indentation randomisation required; Brinell ball condition documented; test block calibration within 90 days
- **Vision system** — illumination intensity, gain, and edge threshold settings version-controlled and frozen before study
- **Functional test fixtures** — fixture wear is a primary EV source; fixture re-qualification interval must be part of the control plan

---

### NIST / National metrology (ISO/IEC 17025 / VIM)

**Key standards:** NIST Handbook 44 · VIM (JCGM 200:2012) · ISO/IEC 17025:2017 · ILAC P14

> In accredited calibration laboratories, GR&R variance components map directly to **Type A** measurement uncertainty — but the preferred language is measurement uncertainty (MU), not %GR&R.

#### Mapping GR&R to uncertainty budget

| GR&R Component | Uncertainty equivalent | Distribution |
|----------------|----------------------|-------------|
| EV (Repeatability) | Type A, within-lab | Normal |
| AV (Reproducibility) | Type A, between-operator | Normal |
| PV (Part Variation) | Not an uncertainty source — it is the measurand variability | — |
| Calibration uncertainty of reference | Type B | Normal or rectangular |
| Thermal expansion coefficient × ΔT | Type B | Rectangular |
| Resolution / least count | Type B | Rectangular (u = resolution / 2√3) |

#### Uncertainty budget table structure (ISO/IEC 17025)

| Source (x_i) | Value | Distribution | Divisor | u_i | ν_i |
|--------------|-------|--------------|---------|-----|-----|
| Repeatability (Type A) | s̄ | Normal | 1 | s̄/√n | n−1 |
| Reproducibility (Type A) | s_between | Normal | 1 | s_between | — |
| Reference std. uncertainty | u_ref | Normal | 1 | u_ref | ∞ |
| Thermal expansion | α·L·ΔT | Rectangular | √3 | — | ∞ |
| Resolution | res | Rectangular | 2√3 | — | ∞ |
| **Combined u_c** | | | | √Σu_i² | Welch-Satterthwaite |
| **Expanded U (k=2)** | | | | 2·u_c | 95% confidence |

#### CMC (Calibration and Measurement Capability)
The CMC line in a laboratory's scope of accreditation defines the smallest uncertainty achievable under routine conditions. For a GR&R study to be valid at a metrology lab, the expanded uncertainty U of the reference standard must be ≤ 25% of the tolerance being measured (ILAC P14 rule; some customers require ≤ 10%).

#### Red flags — national metrology

| Flag | Why it matters |
|------|---------------|
| **Expanded U not reported** | ISO/IEC 17025 requires all calibration certificates to state U at k=2; a bare %GR&R number is insufficient for accreditation records. |
| **k factor not stated** | Coverage factor k must be declared alongside U; different labs use different k values; cross-lab comparisons are invalid without it. |
| **Degrees of freedom not tracked** | Welch-Satterthwaite effective ν must be computed to validate that k=2 achieves the claimed 95% confidence; ν < 10 requires k > 2. |
| **Reference standard not in scope** | The reference used for the study must appear in the laboratory's current accreditation scope; expired or out-of-scope use is a nonconformity. |
| **Environmental conditions not logged** | Temperature, humidity, and barometric pressure must be recorded for every measurement in a 17025 study. |
| **No proficiency testing participation** | ISO/IEC 17025 requires participation in interlaboratory comparisons (PT) for all claimed scopes; a laboratory with no PT record cannot demonstrate metrological traceability. |

#### By instrument type — national metrology

- **Dead-weight tester** — piston-cylinder area documented with thermal expansion correction; air buoyancy correction required above 10 kPa
- **Gage blocks** — wringing film thickness (≈ 0.01 µm) is a systematic EV source; gage block material must match workpiece CTE for temperature compensation
- **Laser interferometer** — refractive index of air correction (Edlén formula) required; vibration isolation and thermal enclosure mandatory
- **Precision balance** — magnetic susceptibility of weight set vs. mass piece must be matched; electrostatic discharge from plastic parts is the primary EV source below 1 mg
- **Reference thermometer** — self-heating current must be characterised and corrected; calibrated at the exact immersion depth used in the study

---

### Healthcare / clinical laboratory (CLIA / ISO 15189)

**Key standards:** CLIA 42 CFR Part 493 · ISO 15189:2022 · CLSI EP05-A3 · CLSI EP15-A3

> In clinical laboratories, the equivalent of an operator is an **analyst**, and the equivalent of a trial run is a **run** (or **replicate**). Precision is decomposed into within-run, between-run, and between-day components — which map directly to EV, AV, and a third temporal component not captured by standard AIAG GR&R.

#### Mapping AIAG GR&R to clinical precision

| AIAG Component | Clinical equivalent | CLSI term |
|---------------|---------------------|-----------|
| EV (within-operator) | Within-run imprecision | CV_r |
| AV (between-operator) | Between-analyst imprecision | — |
| Part Variation (PV) | Biological variation between patients | CV_bio |
| (not in AIAG) | Between-run imprecision | CV_rr |
| (not in AIAG) | Between-day imprecision | CV_d |

#### Allowable total error and sigma metric

- **Allowable Total Error (TEa)** is the clinical equivalent of engineering tolerance. CLIA proficiency testing criteria define TEa for regulated analytes (e.g., glucose ±10 mg/dL or ±10%, whichever is greater).
- **Sigma metric** = (TEa − |bias|) / CV_total — the clinical equivalent of Cpk. Sigma ≥ 6 is world-class; ≥ 4 is acceptable; < 3 requires immediate corrective action.
- **%Imprecision (%CV)** replaces %GR&R as the primary metric: CV = (SD / mean) × 100%.

#### Red flags — clinical laboratory

| Flag | Why it matters |
|------|---------------|
| **CV > TEa/4** | Imprecision alone consumes more than 25% of the total error budget, leaving insufficient margin for bias. |
| **Sigma metric < 3** | Analytical process is unreliable for patient decision-making regardless of QC performance. |
| **Bias not evaluated** | CLIA and ISO 15189 require both precision and bias (trueness) characterisation; GR&R alone is insufficient. |
| **Matrix not matched** | Clinical samples have complex matrices; precision studies must use patient-like material (commutable matrix), not pure aqueous standards. |
| **No inter-run replication** | Within-run CV underestimates total imprecision; between-run and between-day components are required for a complete precision profile (CLSI EP05-A3). |
| **Frozen samples refrozen multiple times** | Repeated freeze-thaw cycles increase analyte degradation, inflating apparent imprecision. |

#### Study design — clinical laboratory

| Consideration | Guidance |
|---------------|----------|
| **Precision levels** | Evaluate at least 2 concentrations: one near the clinical decision point and one at the medical decision limit. |
| **Replicate structure** | CLSI EP05-A3 recommends 2 replicates × 2 runs/day × 20 days for a complete precision profile. |
| **Analyst rotation** | Rotate all analysts across all runs; confounded analyst-by-run designs produce biased AV estimates. |
| **Reference materials** | Use commutable, matrix-matched reference materials (JCTLM-listed where available) for bias evaluation. |
| **TEa definition** | Use CLIA criteria for regulated analytes; use biological variation-based criteria (RiliBÄK, RCPA) for unregulated tests. |
| **Sigma metric reporting** | Report sigma metric alongside %CV and bias in the validation summary; regulatory bodies increasingly expect it. |

#### By instrument type — clinical laboratory

- **Pipette** — gravimetric verification required; tip lot and aspiration speed must be standardised across analysts; static electricity on polypropylene tips is a primary EV source for volumes < 10 µL
- **Analytical balance** — ioniser mandatory below 100 mg; calibration with OIML E2/F1 weights; level bubble checked before each study session
- **Clinical analyzer** — reagent lot must be documented; calibration before study start; QC must pass before each run; maintenance log reviewed
- **Glucometer** — strip lot number is a dominant EV source; CLIA waiver tests require comparisons across multiple strip lots; capillary vs. venous sample is a systematic bias source
- **Spectrophotometer** — wavelength accuracy and stray light verified; cuvette path length uniformity validated; sample temperature thermostatted
- **Centrifuge** — speed (RPM) and time verified with tachometer; rotor balance documented; tube type must match serum/plasma separator requirement

---

### Energy / utilities (ISO 50001 / IEC 61869)

**Key standards:** ISO 50001:2018 · IEC 61869 (instrument transformers) · ASME PTC 19.1 · OIML R 46

#### Meter accuracy classes

Revenue meters are classified by accuracy class defining maximum permissible error (MPE):

| Class | MPE (active energy) | Typical application |
|-------|---------------------|---------------------|
| 0.1 | ±0.1% | Reference / check metering |
| 0.2 | ±0.2% | Revenue metering, transmission |
| 0.5 | ±0.5% | Revenue metering, distribution |
| 1.0 | ±1.0% | Industrial sub-metering |
| 2.0 | ±2.0% | Residential metering |

A GR&R-equivalent study for revenue meters is called a **Measurement and Verification (M&V) protocol** (IPMVP Option D). The %GR&R threshold maps to the M&V measurement uncertainty budget: total uncertainty ≤ 2% of measured energy is the IPMVP baseline.

#### Red flags — energy / utilities

| Flag | Why it matters |
|------|---------------|
| **Instrument transformer ratio error not included** | Current and voltage transformers introduce ratio and phase errors that directly enter the meter reading; their accuracy class must be convolved with the meter's own uncertainty. |
| **M&V baseline period not representative** | An M&V protocol built on atypical operating conditions (partial load, weather outlier) produces invalid energy savings estimates. |
| **Flow meter not calibrated at operating conditions** | Viscosity, density, and Reynolds number at operating temperature affect the meter factor (K-factor); lab calibration at 20°C does not transfer to process conditions. |
| **Grounding and shielding not verified** | High-voltage transient interference is the dominant EV source for revenue meters in substations; EMI shielding must be verified as part of the study. |
| **Burden of current transformer exceeded** | Operating a CT above its rated burden degrades accuracy class; verify connected burden before the study. |
| **No reference meter for comparison** | A GR&R study on a single meter without a certified reference meter cannot detect systematic bias; a transfer standard is required. |

#### Study design — energy / utilities

| Consideration | Guidance |
|---------------|----------|
| **Study design** | Three-operator equivalent: morning shift / afternoon shift / night shift for time-of-use meters; each "operator" represents a temporal operating condition. |
| **Environmental conditions** | Temperature and load profile must be representative of the billing period; summer peak-load and winter base-load are separate study conditions. |
| **Reference standard** | Calibrated reference meter at accuracy class ≥ 0.2% traceable to NIST or equivalent NMI; or portable reference standard at class 0.05. |
| **Measurement uncertainty** | Express results as expanded uncertainty U (k=2) per ASME PTC 19.1; %GR&R and MU are equivalent for billing compliance purposes. |
| **Regulatory threshold** | OIML R 46 requires meters remain within accuracy class MPE throughout the calibration interval; any exceedance is a non-conformance to the billing authority. |
| **M&V protocol** | Document baseline conditions, measurement boundary, and sampling frequency per IPMVP Annex B. |

#### By instrument type — energy / utilities

- **Revenue meter** — sealed, tamper-evident; accuracy class and serial number documented; time-sync via GPS or NTP required for interval metering studies
- **Current transformer** — ratio error and phase displacement tested at 5%, 20%, 100%, and 120% of rated current; class P vs. class PX requirements differ by application
- **Flow meter (turbine/ultrasonic/Coriolis)** — K-factor calibration at operating viscosity; installation effects (upstream straight pipe) must be replicated in study
- **Pressure transmitter** — static pressure effect and temperature coefficient documented; two-point calibration at operating range endpoints
- **Thermocouple** — cold-junction compensation validated; extension cable EMF characterised; immersion depth effect tested at study temperature
- **Power analyzer** — crest factor rating verified against load waveform; harmonic analysis to confirm no spectral aliasing at sampling rate used

---

### Defense / government (MIL-STD / DCSA)

**Key standards:** MIL-STD-45662A · MIL-HDBK-1828 · ANSI/NCSL Z540.3

#### Test Uncertainty Ratio (TUR)

The Defense/government metrology community uses **TUR** (Test Uncertainty Ratio) rather than %GR&R as the primary acceptance criterion:

> **TUR = Tolerance / (2 × U_measurement)** where U_measurement is the expanded uncertainty (k=2) of the measurement system.

- **TUR ≥ 4:1** — ANSI/NCSL Z540.3 default requirement; no guard band required
- **TUR 3:1 to 4:1** — guard banding required; acceptance limit set inside tolerance to compensate for measurement uncertainty
- **TUR < 3:1** — special approval required; document risk acceptance in the calibration record

The %GR&R maps to TUR as: **TUR ≈ Tolerance / (5.15 × σ_GRR)**

#### Guard banding
When TUR < 4:1, the acceptance limit is moved inside the tolerance by the guard band width:
- Guard band = k_GB × U_measurement, where k_GB is chosen to achieve the required false-accept probability
- ANSI/NCSL Z540.3 default: k_GB = 1.0 (one-sided guard band of U_measurement)
- For safety-critical parameters, some programs require k_GB = 2.0

#### Red flags — defense / government

| Flag | Why it matters |
|------|---------------|
| **TUR < 4:1 without guard banding** | Direct Z540.3 violation; product accepted within the measurement uncertainty zone may be non-conforming. |
| **Calibration certificates missing uncertainty statements** | MIL-STD-45662A and Z540.3 require uncertainty on all calibration certificates; a certificate without uncertainty is non-compliant. |
| **Classified hardware study without access log** | DCSA inspection requires a documented chain-of-custody and access log for GR&R studies on classified hardware; unlogged access is a security violation. |
| **Measuring and test equipment not on approved list** | Programs with Government-Furnished Equipment (GFE) requirements must use only approved M&TE; substitutions require Engineering Change Proposal (ECP). |
| **Calibration interval exceeded** | Any M&TE used past its calibration due date invalidates all measurements taken after the last valid calibration. |
| **Environmental monitoring not recorded** | MIL-HDBK-1828 requires temperature, humidity, and vibration monitoring during precision metrology studies. |

#### Study design — defense / government

| Consideration | Guidance |
|---------------|----------|
| **TUR requirement** | TUR ≥ 4:1 per ANSI/NCSL Z540.3; document TUR in the calibration record alongside %GR&R. |
| **Guard banding** | Apply guard band when TUR < 4:1; document guard band width, k_GB value, and false-accept risk in the test procedure. |
| **Classified hardware** | Controlled area required; access log with date/time/personnel for every measurement session. |
| **Documentation** | Calibration record must include: serial number, date, result, uncertainty, TUR, standard used, environmental conditions, technician ID. |
| **Traceability** | NIST traceability is mandatory; for overseas operations, host-nation NMI traceability is acceptable when documented in the calibration procedure. |
| **Interval analysis** | MIL-HDBK-1828 Method 3 (reliability-based interval) is preferred over fixed intervals; recalibration interval extended when in-tolerance rate > 95%. |

#### By instrument type — defense / government

- **Torque wrench (mil-spec)** — calibrated per MIL-DTL-28778; clockwise and counter-clockwise calibrated separately; storage in torque-relief position required
- **Hardness tester** — per MIL-STD-1261; reference test block verified against NIST SRM before each study session
- **CMM** — per ASME B89.4.10348; volumetric performance verified with ball-bar or step gauge; temperature compensation logged
- **Pressure gauge** — deadweight calibration or NIST-traceable piston gauge; hysteresis tested in both directions across full range
- **Electrical multimeter (calibrated)** — EMC shielding verified; lead resistance subtracted for resistance < 1 Ω; RF immunity test for field use
- **Laser range finder** — atmospheric correction (temperature, pressure) applied; retro-target geometry documented; eye-safety class verified before field study

---

## Regulatory Reference

- AIAG *Measurement Systems Analysis Reference Manual*, 4th Edition (2010)
- 21 CFR Part 820.72 — Inspection, Measuring, and Test Equipment (FDA QSR)
- ISO 13485:2016 — Medical devices quality management systems
- IATF 16949:2016 — Automotive quality management systems
- AS9100D / NADCAP AC7130 — Aerospace quality management and measurement systems
- VDA Volume 5 — Automotive measurement systems analysis (German OEM supplement)
- ISO/IEC 17025:2017 — General requirements for calibration and testing laboratories
- ANSI/NCSL Z540.3 — Requirements for the calibration of measuring and test equipment
- CLIA 42 CFR Part 493 — Clinical Laboratory Improvement Amendments
- ISO 15189:2022 — Medical laboratories — Requirements for quality and competence
- ISO 50001:2018 — Energy management systems
- MIL-STD-45662A — Calibration system requirements (U.S. DoD)

Reports generated by this tool are quality records. Retain per applicable document control procedures.
