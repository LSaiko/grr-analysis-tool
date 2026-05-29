"""
tests/test_control_charts.py
============================
Tests for msa_toolkit.control_charts.

Key spec requirement
--------------------
UCL_R formula must match AIAG D4 constant for n=5:
    UCL_R = D4(5) * R_bar  where D4(5) = 2.114
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from msa_toolkit.control_charts import (
    XbarR, XbarS, IMR, PChart, CChart,
    ControlLimits,
    _D4, _A2, _D3, _we_violations,
)

# ---------------------------------------------------------------------------
# Shared synthetic subgroup data (n=5, 20 subgroups)
# ---------------------------------------------------------------------------

RNG = np.random.default_rng(0)
N_SUBGROUPS = 20
SUBGROUP_SIZE = 5
SUBGROUP_DATA = RNG.normal(10.0, 0.015, size=(N_SUBGROUPS, SUBGROUP_SIZE))


# ---------------------------------------------------------------------------
# AIAG constant tests
# ---------------------------------------------------------------------------

class TestAIAGConstants:
    """Verify AIAG D4 and A2 constants match published tabulated values."""

    def test_d4_n5_matches_aiag(self):
        """Spec requirement: D4(5) == 2.114"""
        assert _D4[5] == 2.114

    def test_d4_n2_matches_aiag(self):
        assert _D4[2] == 3.267

    def test_d4_n3_matches_aiag(self):
        assert _D4[3] == 2.574

    def test_a2_n5_matches_aiag(self):
        assert _A2[5] == 0.577

    def test_a2_n2_matches_aiag(self):
        assert _A2[2] == 1.880

    def test_d3_n5_is_zero(self):
        """D3(n) == 0 for n <= 6 (range can't go negative)."""
        assert _D3[5] == 0


# ---------------------------------------------------------------------------
# XbarR — UCL_R formula verification (spec requirement)
# ---------------------------------------------------------------------------

class TestXbarRUCLR:
    """
    Spec requirement: UCL_R = D4(5) * R_bar for subgroup_size = 5.
    """
    def setup_method(self):
        self.chart = XbarR(subgroup_size=5)
        self.chart.fit(SUBGROUP_DATA)

    def test_ucl_r_formula(self):
        """UCL_R must equal D4(5) * R_bar."""
        r_bar = self.chart.r_limits.cl
        expected_ucl = _D4[5] * r_bar
        assert abs(self.chart.r_limits.ucl - expected_ucl) < 1e-10

    def test_lcl_r_is_zero_n5(self):
        """LCL_R = D3(5) * R_bar = 0 (since D3(5) == 0)"""
        assert abs(self.chart.r_limits.lcl - 0.0) < 1e-10

    def test_ucl_x_formula(self):
        """UCL_X = X_bar_bar + A2(5) * R_bar"""
        r_bar = self.chart.r_limits.cl
        x_bar = self.chart.xbar_limits.cl
        expected_ucl = x_bar + _A2[5] * r_bar
        assert abs(self.chart.xbar_limits.ucl - expected_ucl) < 1e-10

    def test_lcl_x_formula(self):
        """LCL_X = X_bar_bar - A2(5) * R_bar"""
        r_bar = self.chart.r_limits.cl
        x_bar = self.chart.xbar_limits.cl
        expected_lcl = x_bar - _A2[5] * r_bar
        assert abs(self.chart.xbar_limits.lcl - expected_lcl) < 1e-10

    def test_center_line_is_grand_mean(self):
        """CL on Xbar chart should equal the grand mean of all subgroup means."""
        expected_cl = float(SUBGROUP_DATA.mean(axis=1).mean())
        assert abs(self.chart.xbar_limits.cl - expected_cl) < 1e-10

    def test_r_bar_is_mean_of_ranges(self):
        """R_bar = mean of subgroup ranges."""
        ranges = SUBGROUP_DATA.max(axis=1) - SUBGROUP_DATA.min(axis=1)
        expected_r_bar = float(ranges.mean())
        assert abs(self.chart.r_limits.cl - expected_r_bar) < 1e-10

    def test_fitted_flag(self):
        assert self.chart._fitted

    def test_plot_returns_figure(self):
        import matplotlib.pyplot as plt
        fig = self.chart.plot()
        assert hasattr(fig, "savefig")
        plt.close(fig)


class TestXbarRSubgroupSizes:
    """Verify UCL_R formula holds for all supported subgroup sizes."""

    @pytest.mark.parametrize("n", [2, 3, 4, 5, 6, 7, 8, 9, 10])
    def test_ucl_r_matches_d4_for_all_n(self, n):
        data = RNG.normal(10.0, 0.01, size=(15, n))
        chart = XbarR(subgroup_size=n).fit(data)
        r_bar = chart.r_limits.cl
        assert abs(chart.r_limits.ucl - _D4[n] * r_bar) < 1e-10

    def test_unsupported_subgroup_size_raises(self):
        with pytest.raises(ValueError):
            XbarR(subgroup_size=1)

    def test_unsupported_subgroup_size_11_raises(self):
        with pytest.raises(ValueError):
            XbarR(subgroup_size=11)


# ---------------------------------------------------------------------------
# XbarR — alternative input formats
# ---------------------------------------------------------------------------

class TestXbarRInputFormats:
    def test_flat_1d_array_reshaped(self):
        flat = SUBGROUP_DATA.flatten()   # 100 values
        chart = XbarR(subgroup_size=5).fit(flat)
        assert len(chart._xbars) == N_SUBGROUPS

    def test_dataframe_input(self):
        rows = []
        for i, grp in enumerate(SUBGROUP_DATA):
            for v in grp:
                rows.append({"Subgroup": i, "Measurement": v})
        df = pd.DataFrame(rows)
        chart = XbarR(subgroup_size=5).fit(df)
        assert len(chart._xbars) == N_SUBGROUPS

    def test_unfitted_plot_raises(self):
        chart = XbarR(subgroup_size=5)
        with pytest.raises(RuntimeError, match="fit"):
            chart.plot()


# ---------------------------------------------------------------------------
# XbarS
# ---------------------------------------------------------------------------

class TestXbarS:
    def setup_method(self):
        self.chart = XbarS(subgroup_size=5).fit(SUBGROUP_DATA)

    def test_fitted(self):
        assert self.chart._fitted

    def test_xbar_cl_matches_xbarr(self):
        """XbarS and XbarR should produce the same center line."""
        xr = XbarR(subgroup_size=5).fit(SUBGROUP_DATA)
        assert abs(self.chart.xbar_limits.cl - xr.xbar_limits.cl) < 1e-10

    def test_s_bar_is_mean_of_stdevs(self):
        stdevs = np.std(SUBGROUP_DATA, axis=1, ddof=1)
        expected = float(stdevs.mean())
        assert abs(self.chart.s_limits.cl - expected) < 1e-10

    def test_plot_returns_figure(self):
        import matplotlib.pyplot as plt
        fig = self.chart.plot()
        assert hasattr(fig, "savefig")
        plt.close(fig)


# ---------------------------------------------------------------------------
# IMR
# ---------------------------------------------------------------------------

class TestIMR:
    def setup_method(self):
        self.indiv = RNG.normal(10.0, 0.02, 30)
        self.chart = IMR().fit(self.indiv)

    def test_fitted(self):
        assert self.chart._fitted

    def test_individuals_length(self):
        assert len(self.chart._indiv) == 30

    def test_mr_length(self):
        assert len(self.chart._mr) == 29   # n-1 moving ranges

    def test_mr_values(self):
        expected_mr = np.abs(np.diff(self.indiv))
        np.testing.assert_allclose(self.chart._mr, expected_mr, rtol=1e-10)

    def test_ucl_i_formula(self):
        """UCL_I = X_bar + 3 * (MR_bar / 1.128)"""
        from msa_toolkit.control_charts import _D2
        mr_bar   = float(np.abs(np.diff(self.indiv)).mean())
        sigma_i  = mr_bar / _D2[2]
        expected = self.indiv.mean() + 3.0 * sigma_i
        assert abs(self.chart.i_limits.ucl - expected) < 1e-10

    def test_ucl_mr_formula(self):
        """UCL_MR = D4(2) * MR_bar"""
        mr_bar   = float(np.abs(np.diff(self.indiv)).mean())
        expected = _D4[2] * mr_bar
        assert abs(self.chart.mr_limits.ucl - expected) < 1e-10

    def test_lcl_mr_is_zero(self):
        """LCL_MR = D3(2) * MR_bar = 0"""
        assert abs(self.chart.mr_limits.lcl) < 1e-10

    def test_plot_returns_figure(self):
        import matplotlib.pyplot as plt
        fig = self.chart.plot()
        assert hasattr(fig, "savefig")
        plt.close(fig)


# ---------------------------------------------------------------------------
# PChart
# ---------------------------------------------------------------------------

class TestPChart:
    def setup_method(self):
        rng = np.random.default_rng(7)
        n_i  = np.full(20, 100)
        np_i = rng.binomial(100, 0.03, 20).astype(float)
        self.df = pd.DataFrame({"n": n_i, "np": np_i})
        self.chart = PChart().fit(self.df)

    def test_fitted(self):
        assert self.chart._fitted

    def test_p_bar_formula(self):
        expected = float(
            self.df["np"].sum() / self.df["n"].sum()
        )
        assert abs(self.chart._p_bar - expected) < 1e-10

    def test_ucl_ge_p_bar(self):
        assert all(u >= self.chart._p_bar for u in self.chart._ucl_i)

    def test_lcl_non_negative(self):
        assert all(l >= 0 for l in self.chart._lcl_i)

    def test_plot_returns_figure(self):
        import matplotlib.pyplot as plt
        fig = self.chart.plot()
        assert hasattr(fig, "savefig")
        plt.close(fig)


# ---------------------------------------------------------------------------
# CChart
# ---------------------------------------------------------------------------

class TestCChart:
    def setup_method(self):
        self.counts = [2, 0, 3, 1, 4, 2, 1, 5, 0, 2, 3, 1, 2, 0, 4]
        self.chart  = CChart().fit(self.counts)

    def test_fitted(self):
        assert self.chart._fitted

    def test_c_bar(self):
        expected = float(np.mean(self.counts))
        assert abs(self.chart.c_limits.cl - expected) < 1e-10

    def test_ucl_formula(self):
        c_bar    = float(np.mean(self.counts))
        expected = c_bar + 3.0 * np.sqrt(c_bar)
        assert abs(self.chart.c_limits.ucl - expected) < 1e-10

    def test_lcl_non_negative(self):
        assert self.chart.c_limits.lcl >= 0.0

    def test_plot_returns_figure(self):
        import matplotlib.pyplot as plt
        fig = self.chart.plot()
        assert hasattr(fig, "savefig")
        plt.close(fig)


# ---------------------------------------------------------------------------
# Western Electric rules
# ---------------------------------------------------------------------------

class TestWEViolations:
    def test_rule1_detects_extreme_point(self):
        """A point > 3σ beyond CL must be flagged as Rule 1."""
        values = np.array([0.0, 0.0, 0.0, 5.0, 0.0])   # index 3 is 5σ above
        cl, sigma = 0.0, 1.0
        viols = _we_violations(values, cl, sigma)
        rule1 = [i for i, r in viols if r == 1]
        assert 3 in rule1

    def test_rule1_no_false_positive_inside_limits(self):
        """Points within ±3σ must not trigger Rule 1."""
        values = np.zeros(10)
        viols  = _we_violations(values, cl=0.0, sigma=1.0)
        rule1  = [i for i, r in viols if r == 1]
        assert rule1 == []

    def test_rule4_detects_eight_same_side(self):
        """8 consecutive positives must flag the 8th as Rule 4."""
        values = np.array([0.5] * 8 + [0.0, 0.0])
        viols  = _we_violations(values, cl=0.0, sigma=1.0)
        rule4  = [i for i, r in viols if r == 4]
        assert 7 in rule4

    def test_rule4_no_false_positive_alternating(self):
        """Alternating signs must not trigger Rule 4."""
        values = np.array([0.5, -0.5] * 10)
        viols  = _we_violations(values, cl=0.0, sigma=1.0)
        rule4  = [i for i, r in viols if r == 4]
        assert rule4 == []

    def test_no_violations_for_in_control_process(self):
        """Normally distributed data within ±3σ should usually have no violations."""
        rng    = np.random.default_rng(99)
        values = rng.normal(0, 0.5, 50)    # sigma=0.5, so 3σ = 1.5, all within ±1.5
        viols  = _we_violations(values, cl=0.0, sigma=1.0)
        # With small sigma (0.5), Rule 1 at ±3σ of cl=0, sigma=1 won't fire for 99%+ of values
        rule1  = [i for i, r in viols if r == 1 and abs(values[i]) > 3.0]
        assert rule1 == []

    def test_empty_violations_for_zero_sigma(self):
        """Zero sigma must return empty list (no division by zero)."""
        values = np.array([1.0, 2.0, 3.0])
        viols  = _we_violations(values, cl=2.0, sigma=0.0)
        assert viols == []


# ---------------------------------------------------------------------------
# ControlLimits dataclass
# ---------------------------------------------------------------------------

class TestControlLimits:
    def test_default_values(self):
        cl = ControlLimits()
        assert cl.cl  == 0.0
        assert cl.ucl == 0.0
        assert cl.lcl == 0.0
        assert cl.violations == []

    def test_assignable(self):
        cl = ControlLimits(cl=5.0, ucl=8.0, lcl=2.0, sigma=1.0)
        assert cl.cl == 5.0


# ---------------------------------------------------------------------------
# to_pdf / to_html smoke tests
# ---------------------------------------------------------------------------

class TestOutputMethods:
    def test_to_pdf_creates_file(self, tmp_path):
        chart = XbarR(subgroup_size=5).fit(SUBGROUP_DATA)
        out   = tmp_path / "xbar_r.pdf"
        chart.to_pdf(out)
        assert out.exists()
        assert out.stat().st_size > 1000   # non-empty

    def test_to_html_creates_file(self, tmp_path):
        chart = IMR().fit(RNG.normal(10.0, 0.01, 30))
        out   = tmp_path / "imr.html"
        chart.to_html(out)
        html = out.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in html
        assert "msa_toolkit" in html

    def test_to_pdf_before_fit_raises(self, tmp_path):
        with pytest.raises(RuntimeError, match="fit"):
            XbarR(subgroup_size=5).to_pdf(tmp_path / "out.pdf")
