# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [2.0.0] — 2026-06

### Fixed
- `requirements.txt`: updated all dependency floors to current supported ranges
  (`pandas>=2.2.0`, `numpy>=1.26.0`, `matplotlib>=3.8.0`, `reportlab>=4.0.0`)
- Python minimum raised to **3.9** (reportlab 4.x requirement)

### Added
- `scipy>=1.11.0` as optional dependency for p-value lookups (graceful fallback when absent)
- Multi-industry study design guide in README: **General manufacturing** (IATF 16949),
  **Aerospace** (AS9100D/NADCAP), **Automotive** (AIAG APQP/PPAP/VDA),
  **NIST/National metrology**, **Healthcare/clinical laboratory** (CLIA/ISO 15189),
  **Energy/utilities** (ISO 50001/IEC 61869), **Defense/government** (MIL-STD/DCSA)
- Togglable (collapsible) example sections in README using GitHub `<details>` blocks
- New cross-industry examples: M1, M2 (manufacturing), A1, A2 (aerospace),
  AU1, AU2 (automotive), H1, H2 (healthcare)
- `BRANCHES.md` documenting the industry-example branch strategy
- `--study-type` flag: `crossed` (default), `nested`, `linearity`, `bias`
- `--usl` / `--lsl` flags for asymmetric tolerance specs; `ndc_tol` secondary metric
- `--attribute` flag for go/no-go attribute agreement analysis (kappa statistic)
- Confidence intervals on all GR&R outputs (chi-squared based, 90% and 95%)
- `--run-order` column support: run chart + Nelson rules 1/2/5/6 detection
- `--compare` flag for multi-study side-by-side comparison report
- Competitive comparison table vs. Minitab / JMP / SigmaXL / QI Macros

---

## [1.1.0] — 2025

### Added
- Renamed marginal output files for clarity
- Interactive HTML dashboard (`grr_dashboard.html`)
- `.gitignore`
- `--version` / `-v` flag

### Added
- `msa_toolkit` package: ANOVA-based GR&R, capability analysis, control charts, CLI

---

## [1.0.0] — 2025

### Added
- Initial release: AIAG MSA 4th Edition crossed GR&R (Average & Range method)
- PDF report via ReportLab Platypus
- Three example datasets (acceptable, marginal, unacceptable)
- Example B (Vernier Caliper) and side-by-side comparison table in README
