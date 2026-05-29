"""
tests/test_capability.py
========================
Tests for msa_toolkit.capability.

Known synthetic dataset
-----------------------
Generated with: np.random.default_rng(42).normal(10.0, 0.0125, 10000)

Expected values (to within stated tolerances):
    mean  ≈ 10.0
    sigma ≈ 0.0125
    LSL = 9.95, USL = 10.05
    Cp  = (10.05 - 9.95) / (6 * 0.0125) = 0.10 / 0.075 = 1.333...
    Cpk ≈ Cp  (when data is well-centered)
"""

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from msa_toolkit.capability import (
    CapabilityResult, process_capability, capability_histogram,
)

# ---------------------------------------------------------------------------
# Shared synthetic dataset  (reproducible via fixed seed)
# ---------------------------------------------------------------------------

RNG = np.random.default_rng(42)
SYNTH_DATA = RNG.normal(loc=10.0, scale=0.0125, size=10000)
LSL, USL = 9.95, 10.05


# ---------------------------------------------------------------------------
# Core capability test (spec requirement: Cp == 1.33 ± 0.01)
# ---------------------------------------------------------------------------

class TestCpSpec:
    """
    Spec requirement: Cp == 1.333 ± 0.01 for the known synthetic dataset.
    """
    def setup_method(self):
        self.result = process_capability(SYNTH_DATA, lsl=LSL, usl=USL)

    def test_cp_within_tolerance(self):
        """Cp must be 1.333 ± 0.01 (spec requirement)."""
        assert abs(self.result.cp - 1.333) <= 0.01, (
            f"Cp = {self.result.cp:.4f}, expected 1.333 ± 0.01"
        )

    def test_cp_formula(self):
        """Cp = (USL - LSL) / (6 * sigma_st)"""
        expected = (USL - LSL) / (6.0 * self.result.sigma_st)
        assert abs(self.result.cp - expected) < 1e-9

    def test_pp_formula(self):
        """Pp = (USL - LSL) / (6 * sigma_lt)"""
        expected = (USL - LSL) / (6.0 * self.result.sigma_lt)
        assert abs(self.result.pp - expected) < 1e-9

    def test_cpk_le_cp(self):
        """Cpk <= Cp always (unless process is perfectly centered)"""
        assert self.result.cpk <= self.result.cp + 1e-9

    def test_ppk_le_pp(self):
        assert self.result.ppk <= self.result.pp + 1e-9

    def test_cpu_cpl_min_is_cpk(self):
        """Cpk = min(CPU, CPL)"""
        expected = min(self.result.cpu, self.result.cpl)
        assert abs(self.result.cpk - expected) < 1e-9

    def test_ppu_ppl_min_is_ppk(self):
        expected = min(self.result.ppu, self.result.ppl)
        assert abs(self.result.ppk - expected) < 1e-9


# ---------------------------------------------------------------------------
# Data acceptance: flat array, DataFrame, DataFrame with Measurement column
# ---------------------------------------------------------------------------

class TestInputFormats:
    def test_flat_list(self):
        r = process_capability(list(SYNTH_DATA[:100]), lsl=LSL, usl=USL)
        assert isinstance(r, CapabilityResult)
        assert r.n == 100

    def test_numpy_array(self):
        r = process_capability(SYNTH_DATA, lsl=LSL, usl=USL)
        assert r.n == len(SYNTH_DATA)

    def test_dataframe_measurement_column(self):
        # Use 2000 samples so sampling variance is small enough to test Cp range
        df = pd.DataFrame({"Measurement": SYNTH_DATA[:2000]})
        r  = process_capability(df, lsl=LSL, usl=USL)
        assert r.n == 2000
        # With n=2000 from N(10, 0.0125), Cp should be 1.333 ± 0.07
        assert abs(r.cp - 1.333) <= 0.07

    def test_dataframe_case_insensitive(self):
        df = pd.DataFrame({"measurement": SYNTH_DATA[:200]})
        r  = process_capability(df, lsl=LSL, usl=USL)
        assert r.n == 200

    def test_dataframe_with_subgroup(self):
        """When Subgroup column present, within-subgroup sigma should be used."""
        n_sg = 5
        n_groups = 50
        data_2d = SYNTH_DATA[: n_sg * n_groups].reshape(n_groups, n_sg)
        rows = []
        for i, grp in enumerate(data_2d):
            for v in grp:
                rows.append({"Subgroup": i, "Measurement": v})
        df = pd.DataFrame(rows)
        r  = process_capability(df, lsl=LSL, usl=USL)
        assert r.sigma_st > 0


# ---------------------------------------------------------------------------
# Cpm computation
# ---------------------------------------------------------------------------

class TestCpm:
    def test_cpm_centered(self):
        """Cpm with target = (LSL+USL)/2 = mean should equal Pp when process centered."""
        r = process_capability(SYNTH_DATA, lsl=LSL, usl=USL, target=10.0)
        assert r.cpm is not None
        # When process is nearly centered, Cpm ≈ Pp (within 5%)
        assert abs(r.cpm - r.pp) / r.pp < 0.05

    def test_cpm_off_target_lower(self):
        """Cpm decreases when target deviates from mean."""
        r_on  = process_capability(SYNTH_DATA, lsl=LSL, usl=USL, target=10.0)
        r_off = process_capability(SYNTH_DATA, lsl=LSL, usl=USL, target=10.02)
        assert r_off.cpm < r_on.cpm


# ---------------------------------------------------------------------------
# Sigma level
# ---------------------------------------------------------------------------

class TestSigmaLevel:
    def test_sigma_level_positive(self):
        r = process_capability(SYNTH_DATA, lsl=LSL, usl=USL)
        assert r.sigma_level > 0

    def test_sigma_level_centered_approx_4(self):
        """For Cpk ≈ 1.33, sigma_level ≈ 4 (3 x 1.33 = 4)"""
        r = process_capability(SYNTH_DATA, lsl=LSL, usl=USL)
        expected = r.cpk * 3.0
        assert abs(r.sigma_level - expected) < 0.01


# ---------------------------------------------------------------------------
# PPM and yield (requires scipy — skipped if unavailable)
# ---------------------------------------------------------------------------

class TestPPMAndYield:
    def test_ppm_and_yield_type(self):
        r = process_capability(SYNTH_DATA, lsl=LSL, usl=USL)
        try:
            import scipy
            assert r.ppm_above_usl is not None
            assert r.ppm_below_lsl is not None
            assert r.yield_estimated is not None
        except ImportError:
            pytest.skip("scipy not installed")

    def test_ppm_positive(self):
        try:
            import scipy
        except ImportError:
            pytest.skip("scipy not installed")
        r = process_capability(SYNTH_DATA, lsl=LSL, usl=USL)
        assert r.ppm_above_usl >= 0
        assert r.ppm_below_lsl >= 0

    def test_yield_between_0_and_1(self):
        try:
            import scipy
        except ImportError:
            pytest.skip("scipy not installed")
        r = process_capability(SYNTH_DATA, lsl=LSL, usl=USL)
        assert 0.0 <= r.yield_estimated <= 1.0


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_lsl_ge_usl_raises(self):
        with pytest.raises(ValueError, match="LSL"):
            process_capability(SYNTH_DATA, lsl=10.05, usl=9.95)

    def test_empty_data_raises(self):
        with pytest.raises((ValueError, Exception)):
            process_capability([], lsl=LSL, usl=USL)

    def test_all_nan_raises(self):
        with pytest.raises((ValueError, Exception)):
            process_capability([float("nan")] * 10, lsl=LSL, usl=USL)


# ---------------------------------------------------------------------------
# Histogram (smoke test — just verifies it returns a Figure)
# ---------------------------------------------------------------------------

class TestHistogram:
    def test_returns_figure(self):
        import matplotlib.pyplot as plt
        r   = process_capability(SYNTH_DATA[:200], lsl=LSL, usl=USL)
        fig = capability_histogram(SYNTH_DATA[:200], r)
        assert hasattr(fig, "savefig")
        plt.close(fig)

    def test_histogram_with_target(self):
        import matplotlib.pyplot as plt
        r   = process_capability(SYNTH_DATA[:200], lsl=LSL, usl=USL, target=10.0)
        fig = capability_histogram(SYNTH_DATA[:200], r, title="Test")
        assert hasattr(fig, "savefig")
        plt.close(fig)


# ---------------------------------------------------------------------------
# Deterministic exact dataset
# ---------------------------------------------------------------------------

class TestExactDataset:
    """
    Generate data with exact known properties by construction.
    100 values equally spread over [mean-3sigma, mean+3sigma].
    For a symmetric linspace the sample std != population std, but
    the ratio (USL-LSL)/(6*sigma_sample) should still be testable.
    """
    def test_cp_exact_formula(self):
        mu, sigma = 10.0, 0.0125
        vals = np.linspace(mu - 3 * sigma, mu + 3 * sigma, 1000)
        r = process_capability(vals, lsl=LSL, usl=USL)
        # Verify formula: Cp = tolerance / (6 * sigma_used)
        expected_cp = (USL - LSL) / (6.0 * r.sigma_st)
        assert abs(r.cp - expected_cp) < 1e-9
