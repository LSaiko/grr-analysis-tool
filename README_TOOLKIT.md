# msa_toolkit

![version](https://img.shields.io/badge/version-0.1.0-blue)
![python](https://img.shields.io/badge/python-%3E%3D3.7-blue)
![standard](https://img.shields.io/badge/standard-AIAG%20MSA%204th%20Ed-orange)
![regulatory](https://img.shields.io/badge/regulatory-21%20CFR%20820.72-red)

An open-source Python package for **Measurement Systems Analysis (MSA)** and
**Statistical Process Control (SPC)** in regulated manufacturing environments.

This package is an open-source continuation of the
[grr-analysis-tool](https://github.com/LSaiko/grr-analysis-tool) (the *Prior
Invention*), extending it with ANOVA-based GR&R decomposition, process
capability indices, and full SPC control chart support. All existing behaviour
in `grr_tool.py` is preserved exactly as-is — every new feature is an
addition, never a modification.

Regulatory context: **21 CFR 820.72** (FDA Inspection, Measuring and Test
Equipment) / **AIAG MSA 4th Edition**.

---

## Module overview

| Module | Description |
|--------|-------------|
| `msa_toolkit.grr` | Re-exports the full public API from `grr_tool.py` — GR&R study (AIAG crossed design, %GRR, NDC, PDF + HTML dashboard) |
| `msa_toolkit.anova` | Two-way crossed ANOVA with variance component decomposition (sigma²_repeatability, sigma²_operator, sigma²_part, sigma²_interaction) |
| `msa_toolkit.capability` | Process capability indices — Cp, Cpk, Pp, Ppk, Cpm, PPM, yield — with matplotlib histogram |
| `msa_toolkit.control_charts` | XbarR, XbarS, IMR, PChart, CChart — all with Western Electric Rules 1–4 violation detection, PDF and HTML output |
| `msa_toolkit.report` | Shared ReportLab PDF building blocks (`make_header`, `make_footer`, `metrics_table`, `embed_chart`) |
| `msa_toolkit.dashboard` | Shared Chart.js HTML helpers (`page_template`, `bar_chart`, `line_chart`, `gauge_meter`, `metrics_grid`) |

---

## Installation

```bash
# Install from the repo root
pip install -e ".[dev]"       # includes scipy + pytest
pip install -e ".[stats]"     # includes scipy only
pip install -e .              # core only (no scipy; p-values and PPM will be None)
```

**Dependencies:** Python ≥ 3.7, pandas, numpy, matplotlib, reportlab  
**Optional:** scipy (for p-values in ANOVA, PPM in capability)

---

## Quick start

### GR&R (existing tool — unchanged)

```bash
# PDF + interactive HTML dashboard
python grr_tool.py --input sample_grr.csv \
    --output grr_report.pdf --dashboard grr_dashboard.html \
    --equipment "Mitutoyo 293-340-30" --operator "QE Team"

# via the new package CLI (identical behaviour)
python -m msa_toolkit grr --input sample_grr.csv \
    --output grr_report.pdf --dashboard grr_dashboard.html
```

### Two-way ANOVA

```bash
python -m msa_toolkit anova \
    --input sample_grr.csv \
    --output anova_report.pdf \
    --dashboard anova_dashboard.html \
    --equipment "CMM SN-001"
```

```python
import pandas as pd
from msa_toolkit.anova import two_way_anova, variance_components, print_anova_table

df = pd.read_csv("sample_grr.csv")
# wide-format CSV → convert to long for ANOVA
df_long = df.melt(
    id_vars=["Part","Operator"], value_vars=["Trial1","Trial2","Trial3"],
    value_name="Measurement"
)
result = two_way_anova(df_long)
print_anova_table(result)
vc = variance_components(result)
print(f"Repeatability σ² = {vc['sigma2_repeatability']:.6f}")
```

### Process capability

```bash
python -m msa_toolkit capability \
    --input measurements.csv \
    --lsl 9.95 --usl 10.05 --target 10.0 \
    --output capability.pdf --dashboard capability.html
```

```python
import numpy as np
from msa_toolkit.capability import process_capability, print_capability_summary

data   = np.random.normal(10.0, 0.0125, 1000)
result = process_capability(data, lsl=9.95, usl=10.05, target=10.0)
print_capability_summary(result)
# Cp = 1.333, Cpk ~ 1.33, PPM ~ 64
```

### Control charts

```bash
# Xbar-R chart
python -m msa_toolkit chart --type xbar-r --input data.csv --subgroup 5 \
    --output xbar_r.pdf --dashboard xbar_r.html

# Individuals and Moving Range
python -m msa_toolkit chart --type i-mr --input data.csv

# P-chart (requires columns: n, np)
python -m msa_toolkit chart --type p --input defects.csv
```

```python
import numpy as np
from msa_toolkit.control_charts import XbarR, IMR, CChart

# XbarR
data  = np.random.normal(10.0, 0.01, (25, 5))   # 25 subgroups of 5
chart = XbarR(subgroup_size=5).fit(data)
print(f"UCL_R = {chart.r_limits.ucl:.5f}")
print(f"Violations: {chart.r_limits.violations}")
fig = chart.plot()
chart.to_pdf("xbar_r.pdf", title="Shaft OD")
chart.to_html("xbar_r.html")

# IMR
imr = IMR().fit(np.random.normal(0, 1, 50))
imr.to_html("imr.html")

# CChart
cc = CChart().fit([2, 0, 3, 1, 4, 2, 1, 5])
cc.to_pdf("cchart.pdf")
```

---

## CLI reference

```
python -m msa_toolkit [grr|anova|capability|chart] [options]

grr          --input CSV  [--output PDF]  [--dashboard HTML]
             [--tolerance FLOAT]  [--equipment STR]  [--generate-sample]

anova        --input CSV  [--output PDF]  [--dashboard HTML]
             [--equipment STR]  [--operator STR]

capability   --input CSV  --lsl FLOAT  --usl FLOAT
             [--target FLOAT]  [--subgroup INT]
             [--output PDF]  [--dashboard HTML]

chart        --type {xbar-r|xbar-s|i-mr|p|c}  --input CSV
             [--subgroup INT]   (required for xbar-r and xbar-s)
             [--output PDF]  [--dashboard HTML]  [--title STR]
```

Omitting a sub-command and passing a `.csv` file directly defaults to `grr`
(backward-compatible with `grr_tool.py` invocations).

---

## Running tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

The test suite covers:

| Test file | Coverage |
|-----------|---------|
| `tests/test_anova.py` | SS values vs. hand-calculated reference, df, MS, F-ratios, variance components, input validation |
| `tests/test_capability.py` | Cp == 1.333 ± 0.01 (spec requirement), all index formulas, Cpm, PPM, yield, error handling |
| `tests/test_control_charts.py` | UCL_R == D4(5) × R̄ (spec requirement), all constant tables, WE rules 1–4, IMR/XbarS/PChart/CChart formulas |

---

## Methodology

### GR&R (grr_tool.py — Prior Invention)
AIAG Crossed GR&R, Average & Range Method.
Study variation expressed as 5.15σ (99% of normal distribution).

### Two-way ANOVA
Balanced crossed design: SS decomposed into Parts, Operators,
Part×Operator Interaction, and Error (repeatability).
Expected Mean Squares used for variance component estimation.
F-statistics compared to F-distribution for p-values (requires scipy).

### Process Capability
- **Short-term σ** (Cp/Cpk): within-subgroup R̄/d₂ (when subgroup info available),
  else overall σ.
- **Long-term σ** (Pp/Ppk): sample standard deviation of all measurements.
- **Cpm**: Taguchi index — accounts for deviation of mean from target.

### Control Charts
All limits computed from AIAG/Shewhart factors:

| Chart | UCL formula |
|-------|------------|
| Xbar-R | X̄̄ ± A₂ × R̄ |
| R-chart | D₄ × R̄ |
| Xbar-S | X̄̄ ± A₃ × S̄ |
| S-chart | B₄ × S̄ |
| I-chart | X̄ ± 3 × (MR̄/d₂) |
| MR-chart | D₄(2) × MR̄ |
| P-chart | p̄ ± 3√(p̄(1−p̄)/nᵢ) |
| C-chart | c̄ ± 3√c̄ |

Western Electric Rules 1–4 are evaluated on every plotted statistic.
Violations are marked with red diamond markers and rule-number labels.

---

## Regulatory reference

- AIAG *Measurement Systems Analysis Reference Manual*, 4th Edition (2010)
- 21 CFR Part 820.72 — Inspection, Measuring, and Test Equipment (FDA QSR)

All PDF reports embed the standard 21 CFR 820.72 footer and are suitable
for inclusion in Device History Records (DHR) or Design History Files (DHF).

---

## Prior Invention attribution

This toolkit extends the **grr-analysis-tool** repository
(https://github.com/LSaiko/grr-analysis-tool), which implements the AIAG
crossed GR&R study with PDF charts and an interactive HTML dashboard.
`msa_toolkit` is an open-source continuation of that work: `grr_tool.py`
remains at the repository root, completely unmodified, and is re-exported
through `msa_toolkit.grr` so that all prior tooling and scripts continue to
function without change.
