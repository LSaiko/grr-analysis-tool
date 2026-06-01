# Branch Strategy

This repository uses a `main`/`master` trunk for the core GR&R tool plus
dedicated `examples/<industry>` branches for industry-specific data and guides.

| Branch | Contents |
|--------|----------|
| `master` | Core GR&R tool (`grr_tool.py`), medical-device examples A/B/C, README |
| `examples/manufacturing` | Examples M1, M2 + manufacturing study guide |
| `examples/aerospace` | Examples A1, A2 + aerospace study guide |
| `examples/automotive` | Examples AU1, AU2 + automotive study guide |
| `examples/healthcare` | Examples H1, H2 + healthcare study guide |
| `examples/nist-metrology` | Metrology/NIST examples + uncertainty budget guide |
| `examples/energy` | Energy/utilities examples |

---

## Per-branch deliverables

Each `examples/<industry>` branch contains:

```
sample_<industry>_<study>.csv     # 2 sample CSV files with realistic data
grr_report_<industry>_<study>.pdf # Pre-generated PDF report
grr_dashboard_<industry>_<study>.html # HTML dashboard
INDUSTRY_GUIDE.md                 # ≤500-word study-design checklist for that sector
```

---

## Creating a branch

```bash
git checkout master
git checkout -b examples/manufacturing
# add files, commit, push
git push -u origin examples/manufacturing
```

---

## Industry branch summaries

### `examples/manufacturing`
- **M1**: Keyence IM-8030 vision system, engine block bore, ±0.015 mm — ACCEPTABLE
- **M2**: Manual thread go/no-go gauge, M8×1.25 — MARGINAL (attribute note)
- Standards: IATF 16949:2016, AIAG APQP 3rd Ed., ISO 9001:2015

### `examples/aerospace`
- **A1**: Renishaw REVO-2 CMM, turbine blade chord, ±0.005 mm — ACCEPTABLE
- **A2**: Manual micrometer, titanium airframe bracket, ±0.010 mm — UNACCEPTABLE
- Standards: AS9100D, NADCAP AC7130, SAE ARP9013

### `examples/automotive`
- **AU1**: Marposs P1000 air gauge, crankshaft journal, ±0.008 mm — ACCEPTABLE
- **AU2**: FARO coordinate arm, body-in-white panel gap, ±1.0 mm — MARGINAL
- Standards: AIAG MSA 4th Ed., AIAG PPAP 4th Ed., VDA Volume 5

### `examples/healthcare`
- **H1**: Eppendorf Research Plus pipette, 100 µL volume, ±2 µL — ACCEPTABLE
- **H2**: Handheld glucometer vs. lab analyzer, blood glucose, ±15% CLIA TEa — UNACCEPTABLE
- Standards: CLIA 42 CFR Part 493, ISO 15189:2022, CLSI EP05-A3

### `examples/nist-metrology`
- Uncertainty budget examples (ISO/IEC 17025 expanded uncertainty language)
- Standards: NIST Handbook 44, VIM (JCGM 200:2012), ISO/IEC 17025:2017, ILAC P14

### `examples/energy`
- Revenue meter, current transformer, flow meter studies
- Standards: ISO 50001:2018, IEC 61869, ASME PTC 19.1, OIML R 46
