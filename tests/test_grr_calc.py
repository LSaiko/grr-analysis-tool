"""
tests/test_grr_calc.py
======================
Pins compute_grr() (AIAG Average & Range method) against numbers that do
NOT come from this tool:

1. The AIAG MSA 4th Ed. reference study (Ch. III, Sec. B, Figs III-B 6 / III-B 15:
   10 parts x 3 appraisers x 3 trials). Intermediates (R-bar per appraiser,
   R-bar-bar, X_diff, Rp, UCL_R) must match the published data sheet exactly;
   percentages must match the published report within 0.1 pp. The residual
   gap is the tool's rounded 5.15-sigma K constants (e.g. K1 = 3.05 vs
   5.15 x 0.5908 = 3.043); %GRR is a ratio, so the 5.15 factor itself cancels.
2. A 2x2x2 study small enough to calculate by hand (arithmetic in comments).
3. The K-constant tables re-derived from the AIAG d2* table (Appendix C).
"""

import math
import random

import pytest

from grr_tool import (
    K1_BY_TRIALS,
    K2_BY_OPERATORS,
    K3_BY_PARTS,
    MeasurementRecord,
    compute_grr,
)

# AIAG MSA 4th Ed. reference data: appraiser -> [trial1, trial2, trial3], parts 1..10
AIAG_DATA = {
    "A": [[0.29, -0.56, 1.34, 0.47, -0.80, 0.02, 0.59, -0.31, 2.26, -1.36],
          [0.41, -0.68, 1.17, 0.50, -0.92, -0.11, 0.75, -0.20, 1.99, -1.25],
          [0.64, -0.58, 1.27, 0.64, -0.84, -0.21, 0.66, -0.17, 2.01, -1.31]],
    "B": [[0.08, -0.47, 1.19, 0.01, -0.56, -0.20, 0.47, -0.63, 1.80, -1.68],
          [0.25, -1.22, 0.94, 1.03, -1.20, 0.22, 0.55, 0.08, 2.12, -1.62],
          [0.07, -0.68, 1.34, 0.20, -1.28, 0.06, 0.83, -0.34, 2.19, -1.50]],
    "C": [[0.04, -1.38, 0.88, 0.14, -1.46, -0.29, 0.02, -0.46, 1.77, -1.49],
          [-0.11, -1.13, 1.09, 0.20, -1.07, -0.67, 0.01, -0.56, 1.45, -1.77],
          [-0.15, -0.96, 0.67, 0.11, -1.45, -0.49, 0.21, -0.49, 1.87, -2.16]],
}


def aiag_records():
    return [
        MeasurementRecord(f"P{p + 1:02d}", op, [trial[p] for trial in trials])
        for op, trials in AIAG_DATA.items()
        for p in range(10)
    ]


@pytest.fixture(scope="module")
def aiag():
    return compute_grr(aiag_records(), 10, 3, 3)


def test_aiag_reference_intermediates(aiag):
    # Published data sheet values
    r_bars = {op.name: op.r_bar for op in aiag.operator_stats}
    x_bars = {op.name: op.x_bar for op in aiag.operator_stats}
    assert r_bars == pytest.approx({"A": 0.184, "B": 0.513, "C": 0.328}, abs=5e-4)
    assert x_bars == pytest.approx({"A": 0.1903, "B": 0.0683, "C": -0.2543}, abs=5e-5)
    assert aiag.r_bar_bar == pytest.approx(0.3417, abs=5e-5)
    assert aiag.x_diff == pytest.approx(0.4446, abs=1e-4)   # sheet subtracts rounded means
    assert aiag.rp == pytest.approx(3.5111, abs=5e-5)
    assert aiag.ucl_r == pytest.approx(0.8795, abs=5e-4)    # D4 = 2.574
    assert aiag.grand_mean == pytest.approx(0.0014, abs=5e-5)


def test_aiag_reference_percentages(aiag):
    # Published GR&R report: %EV 17.62, %AV 20.04, %GRR 26.68, %PV 96.38, ndc 5
    assert aiag.pct_ev == pytest.approx(17.62, abs=0.1)
    assert aiag.pct_av == pytest.approx(20.04, abs=0.1)
    assert aiag.pct_grr == pytest.approx(26.68, abs=0.1)
    assert aiag.pct_pv == pytest.approx(96.38, abs=0.1)
    assert aiag.ndc == 5
    assert aiag.status == "MARGINAL"
    assert not aiag.av_clamped
    # The manual's own example flags appraiser B, part 4: 1.03 - 0.01 = 1.02 > UCL_R 0.880
    assert aiag.out_of_control == [("B", "P04", pytest.approx(1.02))]


def test_aiag_reference_sigma_components(aiag):
    # Published sigma-unit components; the tool reports 5.15-sigma, so divide back.
    # Tolerance 0.5% covers the K-constant rounding.
    published = {"ev": 0.20188, "av": 0.22963, "grr": 0.30575, "pv": 1.10456, "tv": 1.14610}
    for name, sigma in published.items():
        assert getattr(aiag, name) / 5.15 == pytest.approx(sigma, rel=5e-3), name


def test_variance_identities(aiag):
    assert aiag.grr ** 2 == pytest.approx(aiag.ev ** 2 + aiag.av ** 2)
    assert aiag.tv ** 2 == pytest.approx(aiag.grr ** 2 + aiag.pv ** 2)
    assert aiag.pct_grr ** 2 + aiag.pct_pv ** 2 == pytest.approx(100 ** 2)


def test_hand_calculated_2x2x2():
    #          P1          P2
    #   X   [1.0, 1.2]  [2.0, 2.2]
    #   Y   [1.3, 1.5]  [2.3, 2.5]
    # Every range = 0.2 -> R-bar-bar = 0.2
    # X-bar_X = (1.1 + 2.1)/2 = 1.6, X-bar_Y = 1.9 -> X_diff = 0.3
    # part averages 1.25, 2.25 -> Rp = 1.0
    # K1(2 trials) = 4.56, K2(2 ops) = 3.65, K3(2 parts) = 3.65
    # EV  = 0.2 * 4.56                               = 0.912
    # AV^2 = (0.3*3.65)^2 - 0.912^2/(2*2) = 1.199025 - 0.207936 = 0.991089
    # GRR^2 = 0.831744 + 0.991089                    = 1.822833
    # PV  = 1.0 * 3.65                               = 3.65
    # TV^2 = 1.822833 + 13.3225                      = 15.145333
    # %GRR = 100*sqrt(1.822833/15.145333)            = 34.692
    # ndc = floor(1.41 * 3.65 / 1.350123)            = floor(3.812) = 3
    recs = [
        MeasurementRecord("P1", "X", [1.0, 1.2]), MeasurementRecord("P2", "X", [2.0, 2.2]),
        MeasurementRecord("P1", "Y", [1.3, 1.5]), MeasurementRecord("P2", "Y", [2.3, 2.5]),
    ]
    r = compute_grr(recs, 2, 2, 2, tolerance=5.0)
    assert r.r_bar_bar == pytest.approx(0.2)
    assert r.x_diff == pytest.approx(0.3)
    assert r.rp == pytest.approx(1.0)
    assert r.ev == pytest.approx(0.912)
    assert r.av == pytest.approx(math.sqrt(0.991089))
    assert r.grr == pytest.approx(math.sqrt(1.822833))
    assert r.pv == pytest.approx(3.65)
    assert r.tv == pytest.approx(math.sqrt(15.145333))
    assert r.pct_grr == pytest.approx(34.692, abs=1e-3)
    assert r.ndc == 3
    assert r.status == "UNACCEPTABLE"
    # %Tolerance = 100 * GRR / tol = 100 * 1.350123 / 5
    assert r.pct_tol_grr == pytest.approx(27.0025, abs=1e-3)


def test_av_clamped_to_zero_when_operators_agree():
    # Identical operator means -> X_diff = 0 -> AV^2 = -EV^2/(n*r) < 0 -> clamp.
    recs = [
        MeasurementRecord("P1", "X", [1.0, 1.2]), MeasurementRecord("P2", "X", [2.0, 2.2]),
        MeasurementRecord("P1", "Y", [1.2, 1.0]), MeasurementRecord("P2", "Y", [2.2, 2.0]),
    ]
    r = compute_grr(recs, 2, 2, 2)
    assert r.av_clamped and r.av == 0.0
    assert r.grr == pytest.approx(r.ev)


def test_usl_lsl_resolve_tolerance(aiag):
    r = compute_grr(aiag_records(), 10, 3, 3, usl=3.0, lsl=-3.0)
    assert r.tolerance == pytest.approx(6.0)
    assert r.pct_tol_grr == pytest.approx(100 * aiag.grr / 6.0)
    assert r.pct_grr == pytest.approx(aiag.pct_grr)  # tolerance never changes %TV


def test_row_order_does_not_change_metrics(aiag):
    recs = aiag_records()
    random.Random(0).shuffle(recs)
    r = compute_grr(recs, 10, 3, 3)
    for name in ("ev", "av", "grr", "pv", "tv", "pct_grr", "ndc"):
        assert getattr(r, name) == pytest.approx(getattr(aiag, name)), name


@pytest.mark.xfail(strict=True, reason="out_of_control zips CSV row order against sorted part "
                   "names; mislabels parts when the CSV is not sorted by part")
def test_out_of_control_part_labels_follow_data_not_row_order():
    recs = [
        MeasurementRecord("P2", "X", [2.0, 2.0]), MeasurementRecord("P1", "X", [1.0, 1.9]),
        MeasurementRecord("P1", "Y", [1.0, 1.0]), MeasurementRecord("P2", "Y", [2.0, 2.0]),
    ]
    r = compute_grr(recs, 2, 2, 2)
    assert [(op, part) for op, part, _ in r.out_of_control] == [("X", "P1")]


# AIAG MSA 4th Ed. Appendix C d2* values.
# Trials: m = n_trials, g = parts x operators > 15 -> d2 (large g).
# Operators / parts: g = 1 (a single range across operator / part averages).
D2_TRIALS = {2: 1.128, 3: 1.693, 4: 2.059, 5: 2.326}
D2_STAR_G1 = {2: 1.41421, 3: 1.91155, 4: 2.23887, 5: 2.48124, 6: 2.67253,
              7: 2.82981, 8: 2.96288, 9: 3.07794, 10: 3.17905}


@pytest.mark.parametrize("table,d2", [
    (K1_BY_TRIALS, D2_TRIALS),
    (K2_BY_OPERATORS, D2_STAR_G1),
    (K3_BY_PARTS, D2_STAR_G1),
])
def test_k_constants_match_5_15_over_d2(table, d2):
    for m, k in table.items():
        assert k == pytest.approx(5.15 / d2[m], abs=0.01), m
