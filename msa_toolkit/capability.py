"""
msa_toolkit.capability
======================
Process capability indices for SPC and product acceptance in regulated
manufacturing environments.

Implements:
  - Cp, Cpk  — short-term (within-subgroup) indices
  - Pp, Ppk  — long-term (overall) indices
  - Cpm      — Taguchi index (requires target)
  - ppm_above_usl, ppm_below_lsl, yield_estimated
  - sigma_level (number of sigmas to nearest spec limit)

The function accepts either:
  - A 1-D ``array_like`` (individual measurements) — uses overall std
    for all indices (short-term == long-term for ungrouped data)
  - A ``pd.DataFrame`` with a ``Measurement`` column and an optional
    ``Subgroup`` column — uses within-subgroup R-bar/d2 for Cp/Cpk

Regulatory context: 21 CFR 820.72 (FDA QSR)

p-values and normal CDF lookups require scipy.  The module remains
usable without scipy but ``ppm_*`` and ``yield_estimated`` will be
``None``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Union

import numpy as np
import pandas as pd

from .report import (
    make_doc, make_header, make_footer, metrics_table,
    section_heading, embed_chart, para_style,
    NAVY, TEAL, ORANGE, GREEN, RED,
)
from .dashboard import (
    page_template, gauge_meter, metrics_grid,
    metrics_table_html,
)

try:
    from scipy.stats import norm as _norm
    _SCIPY = True
except ImportError:
    _SCIPY = False

__all__ = [
    "CapabilityResult",
    "process_capability",
    "capability_histogram",
    "print_capability_summary",
    "build_capability_pdf",
    "build_capability_dashboard",
]

# ---------------------------------------------------------------------------
# d2 constants (subgroup size → d2 for R-bar/d2 within-sigma estimate)
# ---------------------------------------------------------------------------
_D2 = {
    2: 1.128, 3: 1.693, 4: 2.059, 5: 2.326,
    6: 2.534, 7: 2.704, 8: 2.847, 9: 2.970, 10: 3.078,
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class CapabilityResult:
    """
    All process capability metrics for a given dataset and spec limits.

    Attributes:
        n:                Sample size.
        mean:             Sample mean.
        sigma_st:         Short-term (within-subgroup) standard deviation.
        sigma_lt:         Long-term (overall) standard deviation.
        lsl:              Lower Specification Limit.
        usl:              Upper Specification Limit.
        target:           Target / nominal value (optional).

        cp:               Potential capability (Cp = tolerance / 6*sigma_st).
        cpk:              Actual short-term capability (min of CPU, CPL).
        pp:               Potential performance (Pp = tolerance / 6*sigma_lt).
        ppk:              Actual long-term capability.
        cpm:              Taguchi Cpm (None if no target provided).

        cpu:              Short-term upper capability (USL - mean)/(3*sigma_st).
        cpl:              Short-term lower capability (mean - LSL)/(3*sigma_st).
        ppu:              Long-term upper capability.
        ppl:              Long-term lower capability.

        sigma_level:      Min sigma distance to nearest spec limit (sigma_st).
        ppm_above_usl:    Estimated PPM above USL (from normal CDF, sigma_lt).
        ppm_below_lsl:    Estimated PPM below LSL.
        yield_estimated:  Estimated process yield (fraction).
    """
    n:            int   = 0
    mean:         float = 0.0
    sigma_st:     float = 0.0
    sigma_lt:     float = 0.0
    lsl:          float = 0.0
    usl:          float = 0.0
    target:       Optional[float] = None

    cp:           float = 0.0
    cpk:          float = 0.0
    pp:           float = 0.0
    ppk:          float = 0.0
    cpm:          Optional[float] = None

    cpu:          float = 0.0
    cpl:          float = 0.0
    ppu:          float = 0.0
    ppl:          float = 0.0

    sigma_level:      float           = 0.0
    ppm_above_usl:    Optional[float] = None
    ppm_below_lsl:    Optional[float] = None
    yield_estimated:  Optional[float] = None


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------

def process_capability(
    data: Union[Sequence[float], pd.DataFrame],
    lsl: float,
    usl: float,
    target: Optional[float] = None,
    subgroup_size: Optional[int] = None,
) -> CapabilityResult:
    """
    Compute process capability indices for a dataset and spec limits.

    Args:
        data:          1-D array/list of individual measurements **or** a
                       ``pd.DataFrame`` with columns ``Measurement`` (required)
                       and ``Subgroup`` (optional).  When a ``Subgroup``
                       column is present the within-subgroup R-bar/d2 method
                       is used for sigma_st; otherwise sigma_st == sigma_lt.
        lsl:           Lower Specification Limit.
        usl:           Upper Specification Limit.
        target:        Nominal / target value for Cpm.  Defaults to the
                       midpoint of (LSL + USL) / 2 if not provided.
        subgroup_size: Explicit subgroup size for the R-bar/d2 method when
                       ``data`` is a 1-D array.  If ``None`` and data is
                       1-D, sigma_st equals sigma_lt.

    Returns:
        Populated :class:`CapabilityResult`.

    Raises:
        ValueError: If ``lsl >= usl`` or data is empty.

    Example:
        >>> import numpy as np
        >>> rng = np.random.default_rng(42)
        >>> data = rng.normal(10.0, 0.0125, 1000)
        >>> result = process_capability(data, lsl=9.95, usl=10.05)
        >>> assert abs(result.cp - 1.333) <= 0.01
    """
    if lsl >= usl:
        raise ValueError(f"LSL ({lsl}) must be less than USL ({usl}).")

    # ── Extract measurements ───────────────────────────────────────────────
    if isinstance(data, pd.DataFrame):
        col_map = {c.lower().strip(): c for c in data.columns}
        if "measurement" not in col_map:
            raise ValueError("DataFrame must have a 'Measurement' column.")
        values = data[col_map["measurement"]].values.astype(float)
        # Try to derive within-subgroup sigma from Subgroup column
        if "subgroup" in col_map and subgroup_size is None:
            grp_col = col_map["subgroup"]
            groups  = [
                grp["Measurement"].values
                for _, grp in data.groupby(grp_col)
            ]
            if groups:
                ranges = np.array([g.max() - g.min() for g in groups])
                r_bar  = ranges.mean()
                n_sub  = int(np.median([len(g) for g in groups]))
                if n_sub in _D2:
                    sigma_st_val = r_bar / _D2[n_sub]
                else:
                    sigma_st_val = None
            else:
                sigma_st_val = None
        else:
            sigma_st_val = None
    else:
        values       = np.asarray(data, dtype=float)
        sigma_st_val = None

    values = values[np.isfinite(values)]
    if len(values) == 0:
        raise ValueError("Data contains no finite values.")

    n        = len(values)
    mu       = float(values.mean())
    sigma_lt = float(values.std(ddof=1))   # overall (long-term) sigma

    # Within-subgroup sigma (short-term)
    if sigma_st_val is not None:
        sigma_st = sigma_st_val
    elif subgroup_size is not None and subgroup_size in _D2:
        # Group the flat array into subgroups
        n_complete = (n // subgroup_size) * subgroup_size
        groups = values[:n_complete].reshape(-1, subgroup_size)
        r_bar  = float(np.mean(groups.max(axis=1) - groups.min(axis=1)))
        sigma_st = r_bar / _D2[subgroup_size]
    else:
        sigma_st = sigma_lt   # no subgroup info → treat as individual data

    if sigma_st <= 0 or sigma_lt <= 0:
        raise ValueError("Standard deviation is zero — cannot compute capability.")

    tolerance = usl - lsl

    # ── Short-term (Cp / Cpk) ─────────────────────────────────────────────
    cp  = tolerance / (6.0 * sigma_st)
    cpu = (usl - mu) / (3.0 * sigma_st)
    cpl = (mu - lsl) / (3.0 * sigma_st)
    cpk = min(cpu, cpl)

    # ── Long-term (Pp / Ppk) ──────────────────────────────────────────────
    pp  = tolerance / (6.0 * sigma_lt)
    ppu = (usl - mu) / (3.0 * sigma_lt)
    ppl = (mu - lsl) / (3.0 * sigma_lt)
    ppk = min(ppu, ppl)

    # ── Cpm (Taguchi index) ───────────────────────────────────────────────
    tgt = target if target is not None else (lsl + usl) / 2.0
    tau = math.sqrt(sigma_lt ** 2 + (mu - tgt) ** 2)
    cpm = tolerance / (6.0 * tau) if tau > 0 else None

    # ── Sigma level ───────────────────────────────────────────────────────
    sigma_level = min((usl - mu) / sigma_st, (mu - lsl) / sigma_st)

    # ── PPM and yield (requires scipy) ────────────────────────────────────
    ppm_above = ppm_below = yld = None
    if _SCIPY:
        ppm_above = 1e6 * float(_norm.sf((usl - mu) / sigma_lt))
        ppm_below = 1e6 * float(_norm.cdf((lsl - mu) / sigma_lt))
        yld = 1.0 - (ppm_above + ppm_below) / 1e6

    return CapabilityResult(
        n=n, mean=float(mu),
        sigma_st=float(sigma_st), sigma_lt=float(sigma_lt),
        lsl=lsl, usl=usl, target=tgt,
        cp=cp, cpk=cpk, pp=pp, ppk=ppk, cpm=cpm,
        cpu=cpu, cpl=cpl, ppu=ppu, ppl=ppl,
        sigma_level=float(sigma_level),
        ppm_above_usl=ppm_above,
        ppm_below_lsl=ppm_below,
        yield_estimated=yld,
    )


# ---------------------------------------------------------------------------
# Matplotlib histogram
# ---------------------------------------------------------------------------

def capability_histogram(
    data: Union[Sequence[float], np.ndarray],
    result: CapabilityResult,
    title: str = "Process Capability Histogram",
) -> "plt.Figure":
    """
    Build a capability histogram with LSL/USL/target overlays and normal fit.

    Args:
        data:   Raw measurement values (1-D array-like).
        result: A :class:`CapabilityResult` from :func:`process_capability`.
        title:  Chart title.

    Returns:
        A matplotlib ``Figure``.  Call ``plt.close(fig)`` when done or
        pass to :func:`msa_toolkit.report.embed_chart`.

    Example:
        >>> fig = capability_histogram(data, result, title="Shaft OD Capability")
        >>> fig.savefig("capability.png", dpi=150)
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    values = np.asarray(data, dtype=float)
    values = values[np.isfinite(values)]

    fig, ax = plt.subplots(figsize=(7.0, 3.5), facecolor="white")

    # Histogram
    n_bins = max(10, int(np.sqrt(len(values))))
    ax.hist(values, bins=n_bins, density=True,
            color=TEAL, alpha=0.65, edgecolor="white", zorder=2,
            label="Measurements")

    # Normal-fit curve
    x_fit = np.linspace(values.min() - 3 * result.sigma_lt,
                        values.max() + 3 * result.sigma_lt, 300)
    if _SCIPY:
        from scipy.stats import norm as _norm
        y_fit = _norm.pdf(x_fit, result.mean, result.sigma_lt)
    else:
        # Manual normal PDF
        y_fit = (1.0 / (result.sigma_lt * math.sqrt(2 * math.pi)) *
                 np.exp(-0.5 * ((x_fit - result.mean) / result.sigma_lt) ** 2))
    ax.plot(x_fit, y_fit, color=NAVY, linewidth=1.8, zorder=4, label="Normal fit")

    # Spec lines
    ax.axvline(result.lsl, color=RED,   linestyle="--", linewidth=1.8,
               label=f"LSL = {result.lsl}", zorder=5)
    ax.axvline(result.usl, color=RED,   linestyle="--", linewidth=1.8,
               label=f"USL = {result.usl}", zorder=5)
    ax.axvline(result.mean, color=NAVY, linestyle="-",  linewidth=1.4,
               label=f"Mean = {result.mean:.4f}", zorder=5, alpha=0.7)
    if result.target is not None:
        ax.axvline(result.target, color=GREEN, linestyle=":", linewidth=1.4,
                   label=f"Target = {result.target}", zorder=5)

    # Annotation box
    cpk_color = GREEN if result.cpk >= 1.33 else ORANGE if result.cpk >= 1.00 else RED
    info = (f"Cp = {result.cp:.3f}  Cpk = {result.cpk:.3f}\n"
            f"Pp = {result.pp:.3f}  Ppk = {result.ppk:.3f}\n"
            f"n = {result.n}")
    ax.text(0.01, 0.97, info, transform=ax.transAxes, fontsize=8,
            verticalalignment="top", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor="#D0D3D4", alpha=0.85))

    ax.set_xlabel("Measurement", fontsize=9)
    ax.set_ylabel("Density", fontsize=9)
    ax.set_title(title, fontsize=10, fontweight="bold", pad=8)
    ax.legend(fontsize=7.5, ncol=2, loc="upper right")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.grid(True, linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------

def print_capability_summary(result: CapabilityResult) -> None:
    """
    Print a formatted capability summary to stdout.

    Args:
        result: A :class:`CapabilityResult`.

    Example:
        >>> print_capability_summary(result)
    """
    w = 58
    print()
    print("=" * w)
    print("  PROCESS CAPABILITY".center(w))
    print("=" * w)
    print(f"  n={result.n}   mean={result.mean:.5f}   "
          f"sigma_st={result.sigma_st:.5f}   sigma_lt={result.sigma_lt:.5f}")
    print(f"  LSL={result.lsl}   USL={result.usl}   Target={result.target}")
    print("-" * w)
    print(f"  Cp   = {result.cp:.4f}    Cpk  = {result.cpk:.4f}")
    print(f"  Pp   = {result.pp:.4f}    Ppk  = {result.ppk:.4f}")
    if result.cpm is not None:
        print(f"  Cpm  = {result.cpm:.4f}")
    print(f"  CPU  = {result.cpu:.4f}   CPL  = {result.cpl:.4f}")
    print(f"  Sigma level = {result.sigma_level:.2f}")
    if result.ppm_above_usl is not None:
        print(f"  PPM above USL  = {result.ppm_above_usl:,.1f}")
        print(f"  PPM below LSL  = {result.ppm_below_lsl:,.1f}")
        print(f"  Yield estimate = {result.yield_estimated*100:.4f}%")
    print("-" * w)
    verdict = (
        "Capable (Cpk >= 1.33)"   if result.cpk >= 1.33
        else "Marginal (1.00 <= Cpk < 1.33)" if result.cpk >= 1.00
        else "Incapable (Cpk < 1.00)"
    )
    print(f"  VERDICT: {verdict}")
    print("=" * w)
    print()


# ---------------------------------------------------------------------------
# PDF report
# ---------------------------------------------------------------------------

def build_capability_pdf(
    data: Union[Sequence[float], np.ndarray, pd.DataFrame],
    result: CapabilityResult,
    output_path: Path,
    characteristic: str = "Unspecified",
    study_operator: str = "Quality Engineering",
    title: str = "Process Capability Report",
) -> None:
    """
    Generate a PDF capability report with histogram and metrics tables.

    Args:
        data:            Raw measurement values (for histogram).
        result:          A :class:`CapabilityResult`.
        output_path:     Destination PDF path.
        characteristic:  Name of the measured characteristic / dimension.
        study_operator:  QE name.
        title:           Report title.

    Example:
        >>> build_capability_pdf(data, result, Path("capability.pdf"),
        ...                      characteristic="Shaft OD")
    """
    from reportlab.platypus import Spacer
    from datetime import date

    doc   = make_doc(output_path, title=title, author=study_operator)
    story = []

    story += make_header(
        title=title,
        metadata={
            "Characteristic:": characteristic,
            "Study Performed By:": study_operator,
            "Report Date:": str(date.today()),
            "LSL / USL:": f"{result.lsl} / {result.usl}",
            "Target:": str(result.target) if result.target else "N/A",
            "Regulatory Reference:": "21 CFR 820.72  |  AIAG MSA 4th Edition",
        },
        subtitle="Cp / Cpk / Pp / Ppk Analysis",
    )

    # ── Capability indices table ───────────────────────────────────────────
    story.append(section_heading("Capability Indices"))

    def _cpk_bg(v):
        if v >= 1.33: return "#D5F5E3"
        if v >= 1.00: return "#FDEBD0"
        return "#FADBD8"

    cap_rows = [
        ["Index", "Value", "Sigma Basis", "Interpretation"],
        ["Cp",   f"{result.cp:.4f}",  "Short-term", "Potential (centered)"],
        ["Cpk",  f"{result.cpk:.4f}", "Short-term", "Actual (min CPU/CPL)"],
        ["CPU",  f"{result.cpu:.4f}", "Short-term", "(USL - mean) / 3*sigma_st"],
        ["CPL",  f"{result.cpl:.4f}", "Short-term", "(mean - LSL) / 3*sigma_st"],
        ["Pp",   f"{result.pp:.4f}",  "Long-term",  "Potential (centered)"],
        ["Ppk",  f"{result.ppk:.4f}", "Long-term",  "Actual (min PPU/PPL)"],
    ]
    if result.cpm is not None:
        cap_rows.append(
            ["Cpm", f"{result.cpm:.4f}", "Long-term", "Taguchi (vs. target)"]
        )

    story.append(metrics_table(
        cap_rows,
        col_widths=[0.7, 0.9, 1.2, 3.7],
        highlight_rows=[(2, _cpk_bg(result.cpk)), (6, _cpk_bg(result.ppk))],
    ))
    story.append(Spacer(1, 0.12 * 72))

    # ── Statistics table ───────────────────────────────────────────────────
    story.append(section_heading("Descriptive Statistics"))
    stats_rows = [
        ["Parameter", "Value"],
        ["Sample Size (n)",    str(result.n)],
        ["Mean",               f"{result.mean:.6f}"],
        ["Sigma (short-term)", f"{result.sigma_st:.6f}"],
        ["Sigma (long-term)",  f"{result.sigma_lt:.6f}"],
        ["Sigma Level",        f"{result.sigma_level:.3f}"],
    ]
    if result.ppm_above_usl is not None:
        stats_rows += [
            ["PPM above USL",     f"{result.ppm_above_usl:,.1f}"],
            ["PPM below LSL",     f"{result.ppm_below_lsl:,.1f}"],
            ["Yield (estimated)", f"{result.yield_estimated*100:.4f}%"],
        ]
    story.append(metrics_table(stats_rows, col_widths=[2.5, 4.0]))
    story.append(Spacer(1, 0.12 * 72))

    # ── Histogram ─────────────────────────────────────────────────────────
    story.append(section_heading("Capability Histogram"))
    if isinstance(data, pd.DataFrame):
        col_map = {c.lower().strip(): c for c in data.columns}
        vals = data[col_map.get("measurement", data.columns[0])].values
    else:
        vals = np.asarray(data, dtype=float)
    fig = capability_histogram(vals, result, title=characteristic)
    story += embed_chart(fig, 6.8, 3.5)

    story += make_footer()
    doc.build(story)
    print(f"[+] Capability PDF written to: {output_path}")


# ---------------------------------------------------------------------------
# HTML dashboard
# ---------------------------------------------------------------------------

def build_capability_dashboard(
    result: CapabilityResult,
    output_path: Path,
    characteristic: str = "Unspecified",
    study_operator: str = "Quality Engineering",
    title: str = "Capability Dashboard",
    version: str = "0.1.0",
) -> None:
    """
    Generate a self-contained interactive HTML capability dashboard.

    Args:
        result:         A :class:`CapabilityResult`.
        output_path:    Destination HTML path.
        characteristic: Measured characteristic name.
        study_operator: QE name.
        title:          Dashboard page title.
        version:        msa_toolkit version string.

    Example:
        >>> build_capability_dashboard(result, Path("capability.html"))
    """
    from datetime import date

    def _cpk_css(v):
        return "var(--green)" if v >= 1.33 else "var(--orange)" if v >= 1.00 else "var(--red)"

    kpi_items = [
        ("Cp",   f"{result.cp:.4f}",  "Potential (short-term)",  "var(--navy)"),
        ("Cpk",  f"{result.cpk:.4f}", "Actual (short-term)",     _cpk_css(result.cpk)),
        ("Pp",   f"{result.pp:.4f}",  "Potential (long-term)",   "var(--navy)"),
        ("Ppk",  f"{result.ppk:.4f}", "Actual (long-term)",      _cpk_css(result.ppk)),
        ("Sigma Level", f"{result.sigma_level:.2f}", "Min sigma to spec", "var(--teal)"),
        ("n",    str(result.n),       f"mean = {result.mean:.5f}", "var(--grey)"),
    ]
    if result.ppm_above_usl is not None:
        kpi_items += [
            ("PPM above USL", f"{result.ppm_above_usl:,.0f}", "From normal CDF", "var(--orange)"),
            ("PPM below LSL", f"{result.ppm_below_lsl:,.0f}", "From normal CDF", "var(--orange)"),
        ]
    if result.cpm is not None:
        kpi_items.append(("Cpm", f"{result.cpm:.4f}", "Taguchi index", "var(--teal)"))

    kpi_html = (
        f'<div class="card" style="margin-bottom:18px">'
        f'<h2>Capability Indices &mdash; {characteristic}</h2>'
        f'{metrics_grid(kpi_items)}'
        f'</div>'
    )

    gauge_html = gauge_meter(
        result.cpk * 100.0 / 1.67,   # scale Cpk to 0-100 gauge (1.67 = 5-sigma)
        label="Cpk",
        accept_threshold=1.33 / 1.67 * 100,
        marginal_threshold=1.00 / 1.67 * 100,
        max_value=100.0,
    ).replace('h2>Cpk Gauge', f'h2>Cpk = {result.cpk:.3f}')

    table_rows = [
        ["Index", "Value", "Sigma Basis"],
        ["Cp",  f"{result.cp:.4f}",  "Short-term"],
        ["Cpk", f"{result.cpk:.4f}", "Short-term"],
        ["Pp",  f"{result.pp:.4f}",  "Long-term"],
        ["Ppk", f"{result.ppk:.4f}", "Long-term"],
    ]
    if result.cpm is not None:
        table_rows.append(["Cpm", f"{result.cpm:.4f}", "Long-term"])

    body = (
        kpi_html
        + '<div class="grid grid-2" style="margin-bottom:18px">'
        + gauge_html
        + f'<div class="card"><h2>Spec Summary</h2>'
        + metrics_table_html(
            ["Parameter", "Value"],
            [
                ["LSL", str(result.lsl)],
                ["USL", str(result.usl)],
                ["Target", str(result.target)],
                ["Tolerance", f"{result.usl - result.lsl:.6f}"],
                ["sigma_st", f"{result.sigma_st:.6f}"],
                ["sigma_lt", f"{result.sigma_lt:.6f}"],
            ],
        )
        + "</div></div>"
    )

    html = page_template(
        title=title,
        body_html=body,
        metadata={
            "Characteristic": characteristic,
            "Study by": study_operator,
        },
        version=version,
    )
    output_path.write_text(html, encoding="utf-8")
    print(f"[+] Capability dashboard written to: {output_path}")
