"""
msa_toolkit.control_charts
==========================
SPC control charts with Western Electric Rules 1-4 violation detection.

Available chart classes
-----------------------
- :class:`XbarR`   -- Xbar-R chart pair (subgroup mean + range)
- :class:`XbarS`   -- Xbar-S chart pair (subgroup mean + std dev)
- :class:`IMR`     -- Individuals and Moving Range chart pair
- :class:`PChart`  -- Proportion nonconforming (Binomial)
- :class:`CChart`  -- Count of nonconformities (Poisson)

Each class follows the same interface:

    chart = XbarR(subgroup_size=5)
    chart.fit(data)         # compute CL/UCL/LCL and detect violations
    fig  = chart.plot()     # returns matplotlib Figure
    chart.to_pdf(path)      # save PDF via report.py
    chart.to_html(path)     # save HTML dashboard via dashboard.py

Western Electric Rules (WE 1-4)
--------------------------------
1. One point beyond ±3σ from CL
2. Two of three consecutive points beyond ±2σ (same side)
3. Four of five consecutive points beyond ±1σ (same side)
4. Eight consecutive points on same side of CL

Regulatory context: 21 CFR 820.72 (FDA QSR)
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .report import (
    make_doc, make_header, make_footer,
    metrics_table, section_heading, embed_chart,
    fig_to_image, palette_style,
    NAVY, TEAL, ORANGE, GREEN, RED, GREY,
)
from .dashboard import page_template, line_chart, metrics_table_html, metrics_grid

__all__ = [
    "XbarR", "XbarS", "IMR", "PChart", "CChart",
    "ControlLimits",
]

# ---------------------------------------------------------------------------
# SPC constants
# ---------------------------------------------------------------------------

# d2: expected range / sigma (subgroup size → d2)
_D2 = {2:1.128, 3:1.693, 4:2.059, 5:2.326, 6:2.534,
       7:2.704, 8:2.847, 9:2.970, 10:3.078}

# A2: Xbar-R UCL/LCL factor  (UCL_X = Xbar + A2*Rbar)
_A2 = {2:1.880, 3:1.023, 4:0.729, 5:0.577, 6:0.483,
       7:0.419, 8:0.373, 9:0.337, 10:0.308}

# D3, D4: R-chart LCL/UCL factors
_D3 = {2:0,     3:0,     4:0,     5:0,     6:0,
       7:0.076, 8:0.136, 9:0.184, 10:0.223}
_D4 = {2:3.267, 3:2.574, 4:2.282, 5:2.114, 6:2.004,
       7:1.924, 8:1.864, 9:1.816, 10:1.777}

# A3, B3, B4: Xbar-S chart factors
_A3 = {2:2.659, 3:1.954, 4:1.628, 5:1.427, 6:1.287,
       7:1.182, 8:1.099, 9:1.032, 10:0.975}
_B3 = {2:0,     3:0,     4:0,     5:0,     6:0.030,
       7:0.118, 8:0.185, 9:0.239, 10:0.284}
_B4 = {2:3.267, 3:2.568, 4:2.266, 5:2.089, 6:1.970,
       7:1.882, 8:1.815, 9:1.761, 10:1.716}

# c4: bias correction factor for S-chart
_C4 = {2:0.7979, 3:0.8862, 4:0.9213, 5:0.9400, 6:0.9515,
       7:0.9594, 8:0.9650, 9:0.9693, 10:0.9727}


# ---------------------------------------------------------------------------
# Western Electric Rules
# ---------------------------------------------------------------------------

def _we_violations(values: np.ndarray, cl: float, sigma: float) -> List[Tuple[int, int]]:
    """
    Detect Western Electric Rules 1-4 violations.

    Args:
        values: Array of plotted statistic values.
        cl:     Center line value.
        sigma:  One-sigma distance (not 3-sigma).  The function uses
                multiples of this as zone boundaries.

    Returns:
        List of ``(index, rule_number)`` tuples, one per violation.
        The same index may appear multiple times if it violates > 1 rule.
    """
    violations: List[Tuple[int, int]] = []
    if sigma <= 0:
        return violations
    n   = len(values)
    z   = (values - cl) / sigma    # standardised deviations

    # Rule 1: beyond ±3σ
    for i in range(n):
        if abs(z[i]) > 3.0:
            violations.append((i, 1))

    # Rule 2: 2 of 3 consecutive beyond ±2σ same side
    for i in range(2, n):
        win = z[i - 2: i + 1]
        if sum(1 for w in win if w > 2.0) >= 2:
            violations.append((i, 2))
        elif sum(1 for w in win if w < -2.0) >= 2:
            violations.append((i, 2))

    # Rule 3: 4 of 5 consecutive beyond ±1σ same side
    for i in range(4, n):
        win = z[i - 4: i + 1]
        if sum(1 for w in win if w > 1.0) >= 4:
            violations.append((i, 3))
        elif sum(1 for w in win if w < -1.0) >= 4:
            violations.append((i, 3))

    # Rule 4: 8 consecutive on same side of CL
    for i in range(7, n):
        win = z[i - 7: i + 1]
        if all(w > 0 for w in win) or all(w < 0 for w in win):
            violations.append((i, 4))

    return violations


def _violation_sigma(values: np.ndarray, cl: float, sigma: float) -> float:
    """Return sigma = (UCL - CL) / 3 for WE rule computations."""
    return sigma


# ---------------------------------------------------------------------------
# Shared control limit dataclass
# ---------------------------------------------------------------------------

@dataclass
class ControlLimits:
    """
    Computed control limits for a single sub-chart.

    Attributes:
        cl:          Center line.
        ucl:         Upper Control Limit.
        lcl:         Lower Control Limit (may be 0 for count/range charts).
        sigma:       One-sigma estimate used for WE rules.
        violations:  List of (index, rule) violation tuples.
    """
    cl:         float = 0.0
    ucl:        float = 0.0
    lcl:        float = 0.0
    sigma:      float = 0.0
    violations: List[Tuple[int, int]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class _BaseChart(ABC):
    """Abstract base for all SPC chart classes."""

    _chart_type: str = "Control Chart"

    def __init__(self) -> None:
        self._fitted = False
        self._subgroup_labels: List[str] = []

    @abstractmethod
    def fit(self, data) -> "_BaseChart":
        """Compute control limits and detect WE violations."""

    @abstractmethod
    def plot(self) -> plt.Figure:
        """Return a matplotlib Figure with the chart(s)."""

    def to_pdf(
        self,
        output_path: Path,
        title: str = "",
        equipment: str = "Unspecified",
        study_operator: str = "Quality Engineering",
    ) -> None:
        """
        Save the chart as a single-page PDF.

        Args:
            output_path:    Destination PDF path.
            title:          Report title (defaults to chart type name).
            equipment:      Gage / process identifier.
            study_operator: QE name.

        Example:
            >>> chart.to_pdf(Path("xbar_r.pdf"), title="Shaft OD")
        """
        from reportlab.platypus import Spacer
        from datetime import date

        if not self._fitted:
            raise RuntimeError("Call .fit() before .to_pdf().")

        rpt_title = title or self._chart_type
        doc   = make_doc(output_path, title=rpt_title, author=study_operator)
        story = []
        story += make_header(
            title=rpt_title,
            metadata={
                "Equipment / Process:": equipment,
                "Prepared By:": study_operator,
                "Report Date:": str(date.today()),
                "Regulatory Reference:": "21 CFR 820.72  |  AIAG MSA 4th Edition",
            },
        )
        story.append(section_heading(self._chart_type))
        fig = self.plot()
        story += embed_chart(fig, 6.8, 4.5)
        story += make_footer()
        doc.build(story)
        print(f"[+] {self._chart_type} PDF written to: {output_path}")

    def to_html(
        self,
        output_path: Path,
        title: str = "",
        equipment: str = "Unspecified",
        study_operator: str = "Quality Engineering",
        version: str = "0.1.0",
    ) -> None:
        """
        Save the chart as a self-contained HTML dashboard.

        Args:
            output_path:    Destination HTML path.
            title:          Dashboard title.
            equipment:      Gage / process identifier.
            study_operator: QE name.
            version:        msa_toolkit version string.

        Example:
            >>> chart.to_html(Path("xbar_r.html"), title="Shaft OD")
        """
        if not self._fitted:
            raise RuntimeError("Call .fit() before .to_html().")
        html = self._build_html(title or self._chart_type, equipment,
                                study_operator, version)
        output_path.write_text(html, encoding="utf-8")
        print(f"[+] {self._chart_type} dashboard written to: {output_path}")

    @abstractmethod
    def _build_html(self, title: str, equipment: str,
                    study_operator: str, version: str) -> str:
        """Build and return the full HTML string."""

    def _violation_summary(self, vlist: List[Tuple[int, int]]) -> str:
        if not vlist:
            return "No Western Electric rule violations detected."
        counts = {}
        for _, rule in vlist:
            counts[rule] = counts.get(rule, 0) + 1
        parts = [f"Rule {r}: {c}" for r, c in sorted(counts.items())]
        return "Violations detected — " + "  |  ".join(parts)

    @staticmethod
    def _plot_violations(
        ax: plt.Axes,
        x_pos: np.ndarray,
        y_vals: np.ndarray,
        violations: List[Tuple[int, int]],
    ) -> None:
        """Overlay violation markers and rule-number labels."""
        viol_map: Dict[int, List[int]] = {}
        for idx, rule in violations:
            viol_map.setdefault(idx, []).append(rule)
        for idx, rules in viol_map.items():
            ax.scatter([x_pos[idx]], [y_vals[idx]],
                       s=80, marker="D", color=RED,
                       zorder=6, linewidths=0)
            label = "/".join(f"R{r}" for r in sorted(set(rules)))
            ax.annotate(label, (x_pos[idx], y_vals[idx]),
                        textcoords="offset points", xytext=(0, 8),
                        ha="center", fontsize=7, color=RED, fontweight="bold")


# ---------------------------------------------------------------------------
# XbarR — Xbar and R chart pair
# ---------------------------------------------------------------------------

class XbarR(_BaseChart):
    """
    Xbar-R chart pair: subgroup mean and range.

    Suitable for subgroup sizes 2 to 10.  Uses AIAG A2, D3, D4 constants.

    Args:
        subgroup_size: Number of observations per subgroup (2–10).

    Example:
        >>> import numpy as np
        >>> rng = np.random.default_rng(42)
        >>> data = rng.normal(10.0, 0.01, size=(25, 5))  # 25 subgroups of 5
        >>> chart = XbarR(subgroup_size=5)
        >>> chart.fit(data)
        >>> fig = chart.plot()
        >>> print(f"UCL_X = {chart.xbar_limits.ucl:.4f}")
        >>> print(f"UCL_R = {chart.r_limits.ucl:.4f}")
    """

    _chart_type = "Xbar-R Chart"

    def __init__(self, subgroup_size: int) -> None:
        super().__init__()
        if subgroup_size not in _A2:
            raise ValueError(
                f"Subgroup size {subgroup_size} not in supported range "
                f"{sorted(_A2.keys())}."
            )
        self.subgroup_size = subgroup_size
        self.xbar_limits: ControlLimits = ControlLimits()
        self.r_limits:    ControlLimits = ControlLimits()
        self._xbars: np.ndarray = np.array([])
        self._ranges: np.ndarray = np.array([])

    def fit(self, data) -> "XbarR":
        """
        Compute Xbar-R control limits from subgroup data.

        Args:
            data: 2-D array-like of shape ``(k_subgroups, subgroup_size)``,
                  or a ``pd.DataFrame`` with columns ``Subgroup`` and
                  ``Measurement``.

        Returns:
            self (for chaining).

        Example:
            >>> chart = XbarR(5).fit(np.random.normal(0, 1, (20, 5)))
        """
        groups = self._parse_subgroups(data)
        n = self.subgroup_size

        self._xbars  = np.array([g.mean() for g in groups])
        self._ranges = np.array([g.max() - g.min() for g in groups])
        self._subgroup_labels = [str(i + 1) for i in range(len(groups))]

        x_bar_bar = self._xbars.mean()
        r_bar     = self._ranges.mean()
        a2, d3, d4 = _A2[n], _D3[n], _D4[n]
        sigma_xbar = a2 * r_bar / 3.0    # 1-sigma for WE rules on Xbar chart
        sigma_r    = r_bar * (d4 - 1) / 3.0  # approx 1-sigma for R chart

        self.xbar_limits = ControlLimits(
            cl=x_bar_bar,
            ucl=x_bar_bar + a2 * r_bar,
            lcl=x_bar_bar - a2 * r_bar,
            sigma=sigma_xbar,
            violations=_we_violations(self._xbars, x_bar_bar, sigma_xbar),
        )
        self.r_limits = ControlLimits(
            cl=r_bar,
            ucl=d4 * r_bar,
            lcl=d3 * r_bar,
            sigma=sigma_r,
            violations=_we_violations(self._ranges, r_bar, sigma_r),
        )
        self._fitted = True
        return self

    def _parse_subgroups(self, data) -> List[np.ndarray]:
        if isinstance(data, pd.DataFrame):
            col_map = {c.lower().strip(): c for c in data.columns}
            if "subgroup" in col_map and "measurement" in col_map:
                sg_col   = col_map["subgroup"]
                meas_col = col_map["measurement"]
                return [
                    grp[meas_col].values.astype(float)
                    for _, grp in data.groupby(sg_col)
                ]
            else:
                # Assume each row is a subgroup
                return [data.iloc[i].values.astype(float)
                        for i in range(len(data))]
        arr = np.asarray(data, dtype=float)
        if arr.ndim == 1:
            n_complete = (len(arr) // self.subgroup_size) * self.subgroup_size
            arr = arr[:n_complete].reshape(-1, self.subgroup_size)
        return [arr[i] for i in range(len(arr))]

    def plot(self) -> plt.Figure:
        """
        Return a two-panel matplotlib Figure (Xbar top, R bottom).

        Returns:
            Matplotlib Figure with violation markers and WE-rule labels.

        Example:
            >>> fig = chart.plot()
            >>> fig.savefig("xbar_r.png", dpi=150)
        """
        if not self._fitted:
            raise RuntimeError("Call .fit() first.")

        x = np.arange(1, len(self._xbars) + 1)
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.0, 5.0),
                                        facecolor="white", sharex=True)
        fig.suptitle("Xbar-R Chart", fontsize=11, fontweight="bold", y=0.98)

        # Xbar chart
        self._plot_single(ax1, x, self._xbars, self.xbar_limits,
                          ylabel="Subgroup Mean", title="X-bar Chart")

        # R chart
        self._plot_single(ax2, x, self._ranges, self.r_limits,
                          ylabel="Range", title="R Chart")

        ax2.set_xlabel("Subgroup", fontsize=9)
        fig.tight_layout()
        return fig

    def _plot_single(
        self,
        ax: plt.Axes,
        x: np.ndarray,
        y: np.ndarray,
        limits: ControlLimits,
        ylabel: str,
        title: str,
    ) -> None:
        ax.plot(x, y, marker="o", color=NAVY, linewidth=1.2,
                markersize=5, zorder=3)
        ax.axhline(limits.cl,  color=GREY, linewidth=1.2, zorder=2)
        ax.axhline(limits.ucl, color=RED,  linestyle="--", linewidth=1.3, zorder=2,
                   label=f"UCL = {limits.ucl:.4f}")
        ax.axhline(limits.lcl, color=RED,  linestyle="--", linewidth=1.3, zorder=2,
                   label=f"LCL = {limits.lcl:.4f}")
        self._plot_violations(ax, x, y, limits.violations)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_title(title, fontsize=9, fontweight="bold")
        ax.legend(fontsize=7.5, loc="upper right")
        palette_style(ax)

    def _build_html(self, title, equipment, study_operator, version) -> str:
        x_labels = self._subgroup_labels
        xbar_chart = line_chart(
            {"Xbar": list(self._xbars)}, x_labels,
            title="X-bar Chart",
            ucl=self.xbar_limits.ucl, lcl=self.xbar_limits.lcl,
            cl=self.xbar_limits.cl, y_label="Subgroup Mean",
            canvas_id="xbar-chart", height_px=260,
        )
        r_chart = line_chart(
            {"Range": list(self._ranges)}, x_labels,
            title="R Chart",
            ucl=self.r_limits.ucl,
            lcl=self.r_limits.lcl if self.r_limits.lcl > 0 else None,
            cl=self.r_limits.cl, y_label="Range",
            canvas_id="r-chart", height_px=260,
        )
        summary = metrics_table_html(
            ["Limit", "Xbar Chart", "R Chart"],
            [
                ["CL",  f"{self.xbar_limits.cl:.5f}",  f"{self.r_limits.cl:.5f}"],
                ["UCL", f"{self.xbar_limits.ucl:.5f}", f"{self.r_limits.ucl:.5f}"],
                ["LCL", f"{self.xbar_limits.lcl:.5f}", f"{self.r_limits.lcl:.5f}"],
                ["Violations",
                 str(len(self.xbar_limits.violations)),
                 str(len(self.r_limits.violations))],
            ],
        )
        body = (
            f'<div class="grid grid-2" style="margin-bottom:18px">'
            + xbar_chart + r_chart + "</div>"
            + f'<div class="card" style="margin-bottom:18px"><h2>Control Limits</h2>{summary}</div>'
        )
        return page_template(
            title=title, body_html=body,
            metadata={"Equipment": equipment, "Study by": study_operator},
            version=version,
        )


# ---------------------------------------------------------------------------
# XbarS — Xbar and S chart pair
# ---------------------------------------------------------------------------

class XbarS(_BaseChart):
    """
    Xbar-S chart pair: subgroup mean and standard deviation.

    Preferred over Xbar-R for subgroup sizes > 10, but this implementation
    supports sizes 2–10 with AIAG A3, B3, B4 constants.

    Args:
        subgroup_size: Number of observations per subgroup (2–10).

    Example:
        >>> chart = XbarS(subgroup_size=5)
        >>> chart.fit(data_2d)
    """

    _chart_type = "Xbar-S Chart"

    def __init__(self, subgroup_size: int) -> None:
        super().__init__()
        if subgroup_size not in _A3:
            raise ValueError(
                f"Subgroup size {subgroup_size} not in {sorted(_A3.keys())}."
            )
        self.subgroup_size = subgroup_size
        self.xbar_limits: ControlLimits = ControlLimits()
        self.s_limits:    ControlLimits = ControlLimits()
        self._xbars:  np.ndarray = np.array([])
        self._stdevs: np.ndarray = np.array([])

    def fit(self, data) -> "XbarS":
        """
        Compute Xbar-S control limits.

        Args:
            data: Same format as :meth:`XbarR.fit`.

        Returns:
            self.
        """
        from .control_charts import _D2
        # Reuse XbarR's subgroup parser
        _tmp = XbarR(self.subgroup_size)
        groups = _tmp._parse_subgroups(data)
        n = self.subgroup_size
        a3, b3, b4 = _A3[n], _B3[n], _B4[n]

        self._xbars  = np.array([g.mean() for g in groups])
        self._stdevs = np.array([g.std(ddof=1) for g in groups])
        self._subgroup_labels = [str(i + 1) for i in range(len(groups))]

        x_bar_bar = self._xbars.mean()
        s_bar     = self._stdevs.mean()
        sigma_xbar = a3 * s_bar / 3.0
        sigma_s    = (b4 - 1) * s_bar / 3.0

        self.xbar_limits = ControlLimits(
            cl=x_bar_bar,
            ucl=x_bar_bar + a3 * s_bar,
            lcl=x_bar_bar - a3 * s_bar,
            sigma=sigma_xbar,
            violations=_we_violations(self._xbars, x_bar_bar, sigma_xbar),
        )
        self.s_limits = ControlLimits(
            cl=s_bar,
            ucl=b4 * s_bar,
            lcl=b3 * s_bar,
            sigma=sigma_s,
            violations=_we_violations(self._stdevs, s_bar, sigma_s),
        )
        self._fitted = True
        return self

    def plot(self) -> plt.Figure:
        """Return two-panel Figure (Xbar top, S bottom)."""
        if not self._fitted:
            raise RuntimeError("Call .fit() first.")
        x = np.arange(1, len(self._xbars) + 1)
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.0, 5.0),
                                        facecolor="white", sharex=True)
        fig.suptitle("Xbar-S Chart", fontsize=11, fontweight="bold", y=0.98)
        _tmp = XbarR(self.subgroup_size)
        _tmp._plot_single(ax1, x, self._xbars, self.xbar_limits,
                          "Subgroup Mean", "X-bar Chart")
        _tmp._plot_single(ax2, x, self._stdevs, self.s_limits,
                          "Std Dev", "S Chart")
        ax2.set_xlabel("Subgroup", fontsize=9)
        fig.tight_layout()
        return fig

    def _build_html(self, title, equipment, study_operator, version) -> str:
        x_labels = self._subgroup_labels
        xbar_c = line_chart({"Xbar": list(self._xbars)}, x_labels,
                             "X-bar Chart",
                             ucl=self.xbar_limits.ucl, lcl=self.xbar_limits.lcl,
                             cl=self.xbar_limits.cl, canvas_id="xs-xbar")
        s_c = line_chart({"S": list(self._stdevs)}, x_labels, "S Chart",
                          ucl=self.s_limits.ucl,
                          lcl=self.s_limits.lcl if self.s_limits.lcl > 0 else None,
                          cl=self.s_limits.cl, canvas_id="xs-s")
        body = (f'<div class="grid grid-2" style="margin-bottom:18px">'
                + xbar_c + s_c + "</div>")
        return page_template(title=title, body_html=body,
                             metadata={"Equipment": equipment}, version=version)


# ---------------------------------------------------------------------------
# IMR — Individuals and Moving Range chart pair
# ---------------------------------------------------------------------------

class IMR(_BaseChart):
    """
    Individuals and Moving Range chart pair.

    Appropriate for individual measurements with no natural subgrouping.
    Uses d2(2) = 1.128 for sigma estimation.

    Example:
        >>> chart = IMR()
        >>> chart.fit([10.1, 9.9, 10.3, 10.0, 9.8, 10.2])
    """

    _chart_type = "I-MR Chart"

    def __init__(self) -> None:
        super().__init__()
        self.i_limits:  ControlLimits = ControlLimits()
        self.mr_limits: ControlLimits = ControlLimits()
        self._indiv: np.ndarray = np.array([])
        self._mr:    np.ndarray = np.array([])

    def fit(self, data) -> "IMR":
        """
        Compute I-MR control limits.

        Args:
            data: 1-D array-like of individual measurements.

        Returns:
            self.
        """
        if isinstance(data, pd.DataFrame):
            col_map = {c.lower().strip(): c for c in data.columns}
            meas_col = col_map.get("measurement", data.columns[0])
            values = data[meas_col].values.astype(float)
        else:
            values = np.asarray(data, dtype=float)

        values = values[np.isfinite(values)]
        self._indiv = values
        self._mr    = np.abs(np.diff(values))   # MR_i = |x_i - x_{i-1}|
        self._subgroup_labels = [str(i + 1) for i in range(len(values))]

        x_bar  = float(values.mean())
        mr_bar = float(self._mr.mean()) if len(self._mr) > 0 else 0.0

        # sigma_I = MR_bar / d2(2) = MR_bar / 1.128
        sigma_i  = mr_bar / _D2[2]
        # sigma_MR: use D4(2)=3.267, D3(2)=0
        sigma_mr = mr_bar * (_D4[2] - 1) / 3.0

        self.i_limits = ControlLimits(
            cl=x_bar,
            ucl=x_bar + 3.0 * sigma_i,
            lcl=x_bar - 3.0 * sigma_i,
            sigma=sigma_i,
            violations=_we_violations(values, x_bar, sigma_i),
        )
        self.mr_limits = ControlLimits(
            cl=mr_bar,
            ucl=_D4[2] * mr_bar,
            lcl=0.0,
            sigma=sigma_mr,
            violations=_we_violations(self._mr, mr_bar, sigma_mr),
        )
        self._fitted = True
        return self

    def plot(self) -> plt.Figure:
        """Return two-panel Figure (I top, MR bottom)."""
        if not self._fitted:
            raise RuntimeError("Call .fit() first.")

        x_i  = np.arange(1, len(self._indiv) + 1)
        x_mr = np.arange(2, len(self._indiv) + 1)   # MR starts at i=2

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.0, 5.0),
                                        facecolor="white", sharex=False)
        fig.suptitle("I-MR Chart", fontsize=11, fontweight="bold", y=0.98)

        # Individuals chart
        ax1.plot(x_i, self._indiv, marker="o", color=NAVY,
                 linewidth=1.2, markersize=5, zorder=3)
        ax1.axhline(self.i_limits.cl,  color=GREY, linewidth=1.0, zorder=2)
        ax1.axhline(self.i_limits.ucl, color=RED, linestyle="--",
                    linewidth=1.3, label=f"UCL = {self.i_limits.ucl:.4f}")
        ax1.axhline(self.i_limits.lcl, color=RED, linestyle="--",
                    linewidth=1.3, label=f"LCL = {self.i_limits.lcl:.4f}")
        self._plot_violations(ax1, x_i, self._indiv, self.i_limits.violations)
        ax1.set_ylabel("Individual", fontsize=9)
        ax1.set_title("Individuals Chart", fontsize=9, fontweight="bold")
        ax1.legend(fontsize=7.5, loc="upper right")
        palette_style(ax1)

        # Moving range chart
        ax2.plot(x_mr, self._mr, marker="o", color=TEAL,
                 linewidth=1.2, markersize=5, zorder=3)
        ax2.axhline(self.mr_limits.cl,  color=GREY, linewidth=1.0, zorder=2)
        ax2.axhline(self.mr_limits.ucl, color=RED, linestyle="--",
                    linewidth=1.3, label=f"UCL = {self.mr_limits.ucl:.4f}")
        self._plot_violations(ax2, x_mr, self._mr, self.mr_limits.violations)
        ax2.set_xlabel("Observation", fontsize=9)
        ax2.set_ylabel("Moving Range", fontsize=9)
        ax2.set_title("Moving Range Chart", fontsize=9, fontweight="bold")
        ax2.legend(fontsize=7.5, loc="upper right")
        palette_style(ax2)

        fig.tight_layout()
        return fig

    def _build_html(self, title, equipment, study_operator, version) -> str:
        labels_i  = [str(i + 1) for i in range(len(self._indiv))]
        labels_mr = [str(i + 2) for i in range(len(self._mr))]
        i_c = line_chart({"Individuals": list(self._indiv)}, labels_i,
                          "Individuals Chart",
                          ucl=self.i_limits.ucl, lcl=self.i_limits.lcl,
                          cl=self.i_limits.cl, canvas_id="imr-i")
        mr_c = line_chart({"MR": list(self._mr)}, labels_mr,
                           "Moving Range Chart",
                           ucl=self.mr_limits.ucl, cl=self.mr_limits.cl,
                           canvas_id="imr-mr")
        body = (f'<div class="grid grid-2" style="margin-bottom:18px">'
                + i_c + mr_c + "</div>")
        return page_template(title=title, body_html=body,
                             metadata={"Equipment": equipment}, version=version)


# ---------------------------------------------------------------------------
# PChart — proportion nonconforming
# ---------------------------------------------------------------------------

class PChart(_BaseChart):
    """
    P-chart: proportion nonconforming (variable or fixed sample sizes).

    Args:
        sample_sizes: Optional fixed sample size (int) or list of per-sample
                      sizes.  If ``None``, sizes are read from the data.

    Example:
        >>> import pandas as pd
        >>> df = pd.DataFrame({
        ...     "n":  [100, 100, 100, 95, 100],
        ...     "np": [  3,   5,   2,  4,   1],
        ... })
        >>> chart = PChart()
        >>> chart.fit(df)
    """

    _chart_type = "P-Chart"

    def __init__(self, sample_sizes: Optional[Union[int, List[int]]] = None) -> None:
        super().__init__()
        self._sample_sizes    = sample_sizes
        self._proportions: np.ndarray = np.array([])
        self._n_i:         np.ndarray = np.array([])
        self._ucl_i:       np.ndarray = np.array([])
        self._lcl_i:       np.ndarray = np.array([])
        self._p_bar:       float      = 0.0
        self._violations:  List[Tuple[int, int]] = []

    def fit(self, data) -> "PChart":
        """
        Compute P-chart control limits.

        Args:
            data: DataFrame with columns ``n`` (sample size) and ``np``
                  (number nonconforming), OR a 1-D array of proportions
                  with fixed sample size given at construction.

        Returns:
            self.
        """
        if isinstance(data, pd.DataFrame):
            col_map = {c.lower().strip(): c for c in data.columns}
            # Support either 'np' (count) + 'n' (size) OR 'p' (proportion) + 'n'
            if "np" in col_map and "n" in col_map:
                n_i  = data[col_map["n"]].values.astype(float)
                np_i = data[col_map["np"]].values.astype(float)
                p_i  = np_i / n_i
            elif "p" in col_map and "n" in col_map:
                n_i = data[col_map["n"]].values.astype(float)
                p_i = data[col_map["p"]].values.astype(float)
            else:
                raise ValueError("DataFrame must have columns 'n' and 'np' (or 'p').")
        else:
            p_i = np.asarray(data, dtype=float)
            if self._sample_sizes is None:
                raise ValueError("Provide sample_sizes when fitting from a 1-D array.")
            if isinstance(self._sample_sizes, int):
                n_i = np.full(len(p_i), float(self._sample_sizes))
            else:
                n_i = np.asarray(self._sample_sizes, dtype=float)

        p_bar = float(np.sum(p_i * n_i) / np.sum(n_i))
        ucl_i = p_bar + 3.0 * np.sqrt(p_bar * (1 - p_bar) / n_i)
        lcl_i = np.maximum(0.0, p_bar - 3.0 * np.sqrt(p_bar * (1 - p_bar) / n_i))

        violations = []
        for i, (pi, ucl, lcl) in enumerate(zip(p_i, ucl_i, lcl_i)):
            if pi > ucl or pi < lcl:
                violations.append((i, 1))

        self._proportions = p_i
        self._n_i  = n_i
        self._ucl_i = ucl_i
        self._lcl_i = lcl_i
        self._p_bar = p_bar
        self._violations = violations
        self._subgroup_labels = [str(i + 1) for i in range(len(p_i))]
        self._fitted = True
        return self

    def plot(self) -> plt.Figure:
        """Return single-panel P-chart Figure with variable control limits."""
        if not self._fitted:
            raise RuntimeError("Call .fit() first.")

        x = np.arange(1, len(self._proportions) + 1)
        fig, ax = plt.subplots(figsize=(8.0, 3.5), facecolor="white")
        ax.plot(x, self._proportions, marker="o", color=NAVY,
                linewidth=1.2, markersize=5, zorder=3)
        ax.plot(x, self._ucl_i, color=RED, linestyle="--",
                linewidth=1.2, label="UCL (3σ)", zorder=2)
        ax.plot(x, self._lcl_i, color=RED, linestyle="--",
                linewidth=1.2, label="LCL (3σ)", zorder=2)
        ax.axhline(self._p_bar, color=GREY, linewidth=1.2, zorder=2,
                   label=f"p-bar = {self._p_bar:.4f}")

        # Violation markers (Rule 1 only — beyond variable limits)
        for idx, _ in self._violations:
            ax.scatter([x[idx]], [self._proportions[idx]],
                       s=80, marker="D", color=RED, zorder=6)
            ax.annotate("R1", (x[idx], self._proportions[idx]),
                        textcoords="offset points", xytext=(0, 8),
                        ha="center", fontsize=7, color=RED, fontweight="bold")

        ax.set_xlabel("Sample", fontsize=9)
        ax.set_ylabel("Proportion Nonconforming", fontsize=9)
        ax.set_title("P-Chart — Proportion Nonconforming", fontsize=10,
                     fontweight="bold", pad=8)
        ax.legend(fontsize=7.5, loc="upper right")
        palette_style(ax)
        fig.tight_layout()
        return fig

    def _build_html(self, title, equipment, study_operator, version) -> str:
        labels = self._subgroup_labels
        # For variable limits, we plot UCL/LCL as separate series
        pc = line_chart(
            {"Proportion": list(self._proportions),
             "UCL": list(self._ucl_i),
             "LCL": list(self._lcl_i)},
            labels, "P-Chart", cl=self._p_bar,
            canvas_id="pchart",
        )
        body = f'<div style="margin-bottom:18px">{pc}</div>'
        return page_template(title=title, body_html=body,
                             metadata={"Equipment": equipment}, version=version)


# ---------------------------------------------------------------------------
# CChart — count of nonconformities (Poisson)
# ---------------------------------------------------------------------------

class CChart(_BaseChart):
    """
    C-chart: count of nonconformities (Poisson model, fixed area of opportunity).

    Example:
        >>> chart = CChart()
        >>> chart.fit([2, 0, 3, 1, 4, 2, 1, 5, 0, 2])
    """

    _chart_type = "C-Chart"

    def __init__(self) -> None:
        super().__init__()
        self._counts:  np.ndarray = np.array([])
        self.c_limits: ControlLimits = ControlLimits()

    def fit(self, data) -> "CChart":
        """
        Compute C-chart control limits.

        Args:
            data: 1-D array-like of non-negative integer counts per unit.

        Returns:
            self.
        """
        if isinstance(data, pd.DataFrame):
            col_map = {c.lower().strip(): c for c in data.columns}
            cnt_col = col_map.get("count", col_map.get("c", data.columns[0]))
            counts  = data[cnt_col].values.astype(float)
        else:
            counts = np.asarray(data, dtype=float)

        c_bar  = float(counts.mean())
        sigma  = math.sqrt(c_bar) if c_bar > 0 else 1.0
        ucl    = c_bar + 3.0 * sigma
        lcl    = max(0.0, c_bar - 3.0 * sigma)

        self._counts  = counts
        self.c_limits = ControlLimits(
            cl=c_bar, ucl=ucl, lcl=lcl, sigma=sigma,
            violations=_we_violations(counts, c_bar, sigma),
        )
        self._subgroup_labels = [str(i + 1) for i in range(len(counts))]
        self._fitted = True
        return self

    def plot(self) -> plt.Figure:
        """Return single-panel C-chart Figure."""
        if not self._fitted:
            raise RuntimeError("Call .fit() first.")

        x = np.arange(1, len(self._counts) + 1)
        fig, ax = plt.subplots(figsize=(8.0, 3.5), facecolor="white")
        ax.plot(x, self._counts, marker="o", color=NAVY,
                linewidth=1.2, markersize=5, zorder=3)
        ax.axhline(self.c_limits.cl,  color=GREY, linewidth=1.0, zorder=2,
                   label=f"c-bar = {self.c_limits.cl:.3f}")
        ax.axhline(self.c_limits.ucl, color=RED, linestyle="--",
                   linewidth=1.3, label=f"UCL = {self.c_limits.ucl:.3f}")
        if self.c_limits.lcl > 0:
            ax.axhline(self.c_limits.lcl, color=RED, linestyle="--",
                       linewidth=1.3, label=f"LCL = {self.c_limits.lcl:.3f}")
        self._plot_violations(ax, x, self._counts, self.c_limits.violations)
        ax.set_xlabel("Sample", fontsize=9)
        ax.set_ylabel("Count", fontsize=9)
        ax.set_title("C-Chart — Count of Nonconformities", fontsize=10,
                     fontweight="bold", pad=8)
        ax.legend(fontsize=7.5)
        palette_style(ax)
        fig.tight_layout()
        return fig

    def _build_html(self, title, equipment, study_operator, version) -> str:
        lc = line_chart({"Count": list(self._counts)}, self._subgroup_labels,
                         "C-Chart", ucl=self.c_limits.ucl,
                         lcl=self.c_limits.lcl if self.c_limits.lcl > 0 else None,
                         cl=self.c_limits.cl, canvas_id="cchart")
        body = f'<div style="margin-bottom:18px">{lc}</div>'
        return page_template(title=title, body_html=body,
                             metadata={"Equipment": equipment}, version=version)
