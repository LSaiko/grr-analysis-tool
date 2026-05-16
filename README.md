# GR&R Analysis Tool

![version](https://img.shields.io/badge/version-1.1.0-blue)
![python](https://img.shields.io/badge/python-%3E%3D3.7-blue)
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

Two contrasting studies are included to demonstrate the full range of outcomes.

### Example A — Mitutoyo 293-340-30 (MARGINAL)

> Dataset: [`sample_grr.csv`](sample_grr.csv) · Report: [`grr_report.pdf`](grr_report.pdf) · Dashboard: [`grr_dashboard.html`](grr_dashboard.html)

Precision digital micrometer with small operator biases (0 / +0.003 / −0.002 mm) and low gage noise (σ = 0.002 mm). Part spread ±0.030 mm around nominal 10.000 mm.

### Example B — Vernier Caliper VC-07 (UNACCEPTABLE)

> Dataset: [`sample_grr_unacceptable.csv`](sample_grr_unacceptable.csv) · Report: [`grr_report_unacceptable.pdf`](grr_report_unacceptable.pdf)

Worn vernier caliper with large operator biases (0 / +0.009 / −0.007 mm) and high gage noise (σ = 0.007 mm). Part spread ±0.012 mm around nominal 25.000 mm — tighter tolerance amplifies the measurement system's share of total variation.

### Example C — Zeiss Contura CMM (ACCEPTABLE)

> Dataset: [`sample_grr_acceptable.csv`](sample_grr_acceptable.csv) · Report: [`grr_report_acceptable.pdf`](grr_report_acceptable.pdf)

CMM-class gage with near-zero operator biases (0 / +0.001 / −0.001 mm) and very low gage noise (σ = 0.001 mm). Wide part spread ±0.040 mm around nominal 15.000 mm. Part variation dominates total variation.

---

### Three-example comparison

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
| `grr_tool.py` | Main analysis script (CLI) — v1.1.0 |
| `requirements.txt` | Python dependencies (Python ≥ 3.7) |
| `sample_grr.csv` | Example A dataset — Mitutoyo micrometer |
| `grr_report.pdf` | Example A PDF report — ⚠️ MARGINAL (17.0% GR&R, ndc 8) |
| `grr_dashboard.html` | Example A interactive dashboard — open in any browser |
| `sample_grr_unacceptable.csv` | Example B dataset — Vernier caliper |
| `grr_report_unacceptable.pdf` | Example B PDF report — ❌ UNACCEPTABLE (89.9% GR&R, ndc 0) |
| `sample_grr_acceptable.csv` | Example C dataset — Zeiss CMM |
| `grr_report_acceptable.pdf` | Example C PDF report — ✅ ACCEPTABLE (8.2% GR&R, ndc 17) |

---

## Requirements

```
pandas>=1.5.0
numpy>=1.23.0
matplotlib>=3.6.0
reportlab>=3.6.0
```

Install dependencies:

```bash
pip install -r requirements.txt
```

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

## What to Look Out for in a GR&R Report — Medical Device Industry

GR&R studies in medical device manufacturing carry regulatory weight. A failed or misread study can mean shipping non-conforming product or unnecessarily scrapping acceptable lots. Below are the critical flags per instrument category.

---

### Universal red flags (apply to all gages)

| Flag | Why it matters |
|------|---------------|
| **%GR&R > 30%** | Measurement system cannot reliably distinguish conforming from non-conforming product. Do not use for acceptance decisions. |
| **ndc < 5** | Gage cannot resolve enough categories of part variation. Any SPC or Cpk analysis built on this data is statistically invalid. |
| **AV > EV** | Operator technique is the dominant error source. Training, fixtures, or a jig to enforce consistent contact/orientation usually resolve this before gage replacement is needed. |
| **EV >> AV** | Gage itself is the weak link — worn components, poor resolution, or instrument age. Calibration or replacement required. |
| **%GR&R passes but ndc < 5** | Can happen when part spread is very narrow. Both criteria must pass independently. |
| **Operator range spread > UCL** | One operator's ranges consistently exceed the control limit — indicates erratic technique or undisclosed part-handling damage during the study. |

---

### By instrument type

#### Dimensional gages (micrometers, calipers, height gauges)
- **Typical threshold tightened to ≤ 10%** for critical dimensions on implants or mating surfaces per ISO 13485 supplier expectations
- Watch for **thermal drift** — hand warmth shifts micrometer readings 0.002–0.005 mm on steel; allow 30 min temperature stabilisation before study
- **Caliper jaw wear** is the most common EV driver; check anvil faces under magnification if EV dominates
- Resolution must be ≤ 10% of the tolerance; a 0.01 mm caliper on a ±0.02 mm tolerance will fail regardless of operator skill

#### Coordinate Measuring Machines (CMM)
- CMM GR&R studies must control **fixture repeatability** separately — fixture variation contaminates EV and cannot be separated post-hoc
- **Probe qualification interval** matters: a fouled or worn stylus introduces EV that looks like gage noise
- Programmatic studies (same CNC program, same operator) typically yield %GR&R < 5%; if not, investigate probe force settings and part datum stability
- For soft or compliant materials (silicone, PTFE components), probe force must be validated not to deform the part

#### Force and torque gauges (connector insertion/extraction, torque wrenches)
- **Rate of loading** is a major reproducibility driver — operators who load faster get systematically different readings; standardise dwell time in the work instruction
- Peak-hold vs. real-time reading mode must be consistent across all trials and operators
- Watch for **hysteresis** in the load cell: always approach the target load from the same direction (increasing or decreasing), never mix
- For break-loose torque on fasteners: part fixturing is critical — if the part rotates instead of the fastener, EV will be inflated beyond recovery

#### Hardness testers (Rockwell, Vickers, Shore)
- **Indentation location** must be randomised across the surface, not reusing prior indents — prior indents cause work hardening that inflates readings
- Anvil cleanliness and surface finish of the reference block dominate EV; a grime film of 0.001 mm on the anvil causes meaningful Rockwell error
- Shore durometer studies on elastomers require tightly controlled **contact speed and dwell time** (ASTM D2240); this is the primary AV source in rubber and silicone parts
- For implant-grade titanium and CoCr alloys, verify the indenter tip is not picking up material transfer between trials

#### Surface roughness (profilometers)
- **Traversal direction** relative to machining lay is the largest single reproducibility source — specify direction in the measurement plan and confirm operators follow it
- Cut-off wavelength (λc) selection must be fixed; operators choosing different filters will produce incomparable readings
- Re-positioning on the same nominal surface location between trials introduces significant EV on curved or complex geometries; use a fixture or scribe marks
- GR&R on roughness measurements often yields high %GR&R for parts with Ra < 0.4 µm — consider whether the parameter (Ra vs. Rz vs. Rq) is appropriate for the control requirement

#### Pressure and flow gauges (catheter burst, valve cracking pressure)
- **Fluid temperature** shifts fluid viscosity and directly affects burst and cracking pressure readings; thermostat the test fluid or include temperature as a covariate
- Dead-volume in the test circuit contributes to EV — minimise tubing length between gage and test article and keep it consistent across all trials
- For burst testing, part-to-part variation in wall thickness dominates; if %GR&R appears low but ndc < 5, the test circuit is masking real part variation through compliance
- Single-use assemblies require a fresh sample per trial — avoid re-pressurising a fatigued specimen

#### Electrical and electronic test equipment (impedance analysers, hipot testers, multimeters)
- **Cable and fixture impedance** at high frequencies is a major EV source — fixturing must be included in the GR&R study, not treated as infrastructure
- For production hipot testers, contact resistance at the test probes is the dominant EV driver; verify probe tip condition before every study
- Bioimpedance or RF device measurements are highly sensitive to **grounding and shielding** — run the study in the actual production environment, not a lab bench
- Multimeter GR&R studies on resistance < 1 Ω must use 4-wire Kelvin connections; 2-wire measurements include lead resistance in EV

#### Optical and vision systems (automated inspection, laser micrometers)
- **Lighting intensity drift** over a work shift is a hidden EV source in camera-based systems; verify illuminator warm-up stabilisation time
- Focus repeatability in telecentric optics degrades with temperature; if EV increases between morning and afternoon study sessions, suspect thermal focus shift
- Edge detection threshold settings must be locked and version-controlled — a threshold change between studies invalidates cross-study comparisons
- For laser micrometer studies on transparent or translucent materials (clear tubing, optical fibers), verify the beam does not refract through the part; use appropriate wavelength

#### Weighing and mass measurement
- **Draught shields** are mandatory for balances < 0.1 g resolution; HVAC airflow is the primary EV source without them
- Electrostatic charge on plastic or powder parts causes reading drift; use ioniser or anti-static plate in the weighing area
- Calibrated reference weights must bracket the measurement range; a balance calibrated only at mid-range introduces systematic EV at the extremes
- Zero drift between trials must be corrected; re-zero before every measurement or the prior measurement's residue contaminates EV

---

### Study design considerations for regulated environments

| Consideration | Guidance |
|---------------|----------|
| **Minimum study size** | 10 parts × 3 operators × 3 trials is the AIAG baseline. For critical or life-sustaining device dimensions, some customers require 10 × 3 × 5. |
| **Part selection** | Parts must span the full production tolerance range, not be selected for "convenience." FDA investigators check this. |
| **Blind randomisation** | Operators should not see each other's readings. Parts should be re-coded to prevent memory effects across trials. |
| **Environment** | Conduct the study under production conditions, not controlled lab conditions, unless the gage is exclusively lab-based. |
| **Re-study triggers** | Re-study is required after: equipment repair or replacement, significant process change, new operator qualification, calibration interval expiry, or any out-of-tolerance calibration finding. |
| **Design history file** | For 21 CFR Part 820 compliance, the GR&R study, raw data, and acceptance decision must be retained in the DHF or DMR. |

---

## Regulatory Reference

- AIAG *Measurement Systems Analysis Reference Manual*, 4th Edition (2010)
- 21 CFR Part 820.72 — Inspection, Measuring, and Test Equipment (FDA QSR)

Reports generated by this tool are quality records. Retain per applicable document control procedures.
