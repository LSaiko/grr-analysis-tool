"""
tests/test_anova.py
===================
Tests for msa_toolkit.anova.

Reference dataset (hand-calculated)
-------------------------------------
Design: 3 parts x 2 operators x 2 trials = 12 measurements

    Part 1: Op A [10.1, 10.2], Op B [10.0, 10.1]
    Part 2: Op A [10.5, 10.4], Op B [10.3, 10.4]
    Part 3: Op A [9.8,  9.9],  Op B [9.7,  9.8]

Grand mean = 10.1

Hand-calculated SS values:
    SS_parts       = 0.72     (4 * [0² + 0.3² + 0.3²])
    SS_operators   = 0.03     (6 * [0.05² + 0.05²])
    SS_interaction = 0.0      (all interaction deviations = 0)
    SS_error       = 0.03     (6 cells x 0.005 each)
    SS_total       = 0.78
"""

import math
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import pytest

# Ensure repo root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from msa_toolkit.anova import two_way_anova, variance_components, AnovaResult

# ---------------------------------------------------------------------------
# Reference dataset
# ---------------------------------------------------------------------------

REFERENCE_DATA = pd.DataFrame({
    "Part":        ["P1","P1","P1","P1",
                    "P2","P2","P2","P2",
                    "P3","P3","P3","P3"],
    "Operator":    ["A","A","B","B",
                    "A","A","B","B",
                    "A","A","B","B"],
    "Measurement": [10.1, 10.2, 10.0, 10.1,
                    10.5, 10.4, 10.3, 10.4,
                     9.8,  9.9,  9.7,  9.8],
})

TOL = 1e-6   # tolerance for floating-point comparisons


# ---------------------------------------------------------------------------
# SS value tests (hand-calculated reference)
# ---------------------------------------------------------------------------

class TestSSValues:
    def setup_method(self):
        self.result = two_way_anova(REFERENCE_DATA)

    def test_ss_parts(self):
        """SS_parts = o*r * sum((part_mean - grand_mean)^2) = 4*(0+0.09+0.09) = 0.72"""
        assert abs(self.result.ss_parts - 0.72) < TOL

    def test_ss_operators(self):
        """SS_operators = p*r * sum((op_mean - grand_mean)^2) = 6*(0.0025+0.0025) = 0.03"""
        assert abs(self.result.ss_operators - 0.03) < TOL

    def test_ss_interaction(self):
        """SS_interaction = 0 for this dataset (no interaction by construction)"""
        assert abs(self.result.ss_interaction - 0.0) < TOL

    def test_ss_error(self):
        """SS_error = 6 cells x 0.005 = 0.03"""
        assert abs(self.result.ss_error - 0.03) < TOL

    def test_ss_total(self):
        """SS_total = SS_parts + SS_operators + SS_interaction + SS_error = 0.78"""
        ss_sum = (self.result.ss_parts + self.result.ss_operators
                  + self.result.ss_interaction + self.result.ss_error)
        assert abs(ss_sum - self.result.ss_total) < TOL
        assert abs(self.result.ss_total - 0.78) < TOL


class TestDfValues:
    def setup_method(self):
        self.r = two_way_anova(REFERENCE_DATA)

    def test_df_parts(self):
        assert self.r.df_parts == 2       # p-1 = 3-1

    def test_df_operators(self):
        assert self.r.df_operators == 1   # o-1 = 2-1

    def test_df_interaction(self):
        assert self.r.df_interaction == 2 # (p-1)*(o-1) = 2*1

    def test_df_error(self):
        assert self.r.df_error == 6       # p*o*(r-1) = 3*2*1

    def test_df_total(self):
        assert self.r.df_total == 11      # N-1 = 12-1


class TestMSValues:
    def setup_method(self):
        self.r = two_way_anova(REFERENCE_DATA)

    def test_ms_parts(self):
        expected = 0.72 / 2
        assert abs(self.r.ms_parts - expected) < TOL

    def test_ms_operators(self):
        expected = 0.03 / 1
        assert abs(self.r.ms_operators - expected) < TOL

    def test_ms_error(self):
        expected = 0.03 / 6
        assert abs(self.r.ms_error - expected) < TOL


class TestFRatios:
    def setup_method(self):
        self.r = two_way_anova(REFERENCE_DATA)

    def test_f_parts(self):
        expected = (0.72 / 2) / (0.03 / 6)
        assert abs(self.r.f_parts - expected) < TOL

    def test_f_operators(self):
        expected = (0.03 / 1) / (0.03 / 6)
        assert abs(self.r.f_operators - expected) < TOL

    def test_f_interaction(self):
        """Interaction MS = 0, so F = 0"""
        assert abs(self.r.f_interaction - 0.0) < TOL


# ---------------------------------------------------------------------------
# Grand mean
# ---------------------------------------------------------------------------

class TestGrandMean:
    def test_grand_mean(self):
        r = two_way_anova(REFERENCE_DATA)
        assert abs(r.grand_mean - 10.1) < TOL


# ---------------------------------------------------------------------------
# Variance components
# ---------------------------------------------------------------------------

class TestVarianceComponents:
    def setup_method(self):
        self.r = two_way_anova(REFERENCE_DATA)
        self.vc = variance_components(self.r)

    def test_repeatability_equals_ms_error(self):
        """sigma2_repeatability == MS_error by definition"""
        assert abs(self.vc["sigma2_repeatability"] - self.r.ms_error) < TOL

    def test_interaction_non_negative(self):
        assert self.vc["sigma2_interaction"] >= 0.0

    def test_operator_non_negative(self):
        assert self.vc["sigma2_operator"] >= 0.0

    def test_part_non_negative(self):
        assert self.vc["sigma2_part"] >= 0.0

    def test_total_equals_sum(self):
        total = (self.vc["sigma2_repeatability"]
                 + self.vc["sigma2_interaction"]
                 + self.vc["sigma2_operator"]
                 + self.vc["sigma2_part"])
        assert abs(total - self.vc["sigma2_total"]) < TOL


# ---------------------------------------------------------------------------
# Design dimensions
# ---------------------------------------------------------------------------

class TestDesignDimensions:
    def setup_method(self):
        self.r = two_way_anova(REFERENCE_DATA)

    def test_n_parts(self):
        assert self.r.n_parts == 3

    def test_n_operators(self):
        assert self.r.n_operators == 2

    def test_n_trials(self):
        assert self.r.n_trials == 2

    def test_parts_list(self):
        assert self.r.parts == ["P1", "P2", "P3"]

    def test_operators_list(self):
        assert self.r.operators == ["A", "B"]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_missing_column_raises(self):
        bad = REFERENCE_DATA.drop(columns=["Operator"])
        with pytest.raises(ValueError, match="Operator"):
            two_way_anova(bad)

    def test_case_insensitive_columns(self):
        df = REFERENCE_DATA.rename(columns={
            "Part": "part", "Operator": "operator", "Measurement": "measurement"
        })
        r = two_way_anova(df)
        assert r.n_parts == 3

    def test_unbalanced_raises(self):
        bad = REFERENCE_DATA.iloc[:-1].copy()   # drop last row → unbalanced
        with pytest.raises(ValueError, match="[Uu]nbalanced"):
            two_way_anova(bad)


# ---------------------------------------------------------------------------
# Larger synthetic dataset (numerical stability)
# ---------------------------------------------------------------------------

class TestLargerDataset:
    def test_ss_total_identity(self):
        """SS_parts + SS_ops + SS_interaction + SS_error == SS_total"""
        rng = np.random.default_rng(42)
        rows = []
        for p in range(1, 11):      # 10 parts
            for o in ["A", "B", "C"]:   # 3 operators
                for t in range(3):       # 3 trials
                    val = 10.0 + rng.normal(0, 0.01)
                    rows.append({"Part": f"P{p:02d}",
                                 "Operator": o,
                                 "Measurement": val})
        df = pd.DataFrame(rows)
        r  = two_way_anova(df)
        ss_sum = (r.ss_parts + r.ss_operators
                  + r.ss_interaction + r.ss_error)
        assert abs(ss_sum - r.ss_total) < 1e-9

    def test_f_ratios_positive(self):
        rng = np.random.default_rng(0)
        rows = []
        for p in range(1, 6):
            for o in ["A", "B"]:
                for t in range(2):
                    rows.append({"Part": str(p), "Operator": o,
                                 "Measurement": rng.normal(p, 0.02)})
        r = two_way_anova(pd.DataFrame(rows))
        assert r.f_parts > 0
        assert r.f_operators >= 0
