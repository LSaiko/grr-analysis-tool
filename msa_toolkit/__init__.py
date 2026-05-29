"""
msa_toolkit
===========
An open-source Python package for Measurement Systems Analysis (MSA)
and Statistical Process Control (SPC) in regulated manufacturing
environments.

This package extends the Prior Invention ``grr-analysis-tool``
(github.com/LSaiko/grr-analysis-tool) with additional modules for
ANOVA-based GR&R decomposition, process capability, and control charts.

All existing behaviour in ``grr_tool.py`` is preserved exactly as-is.

Modules
-------
grr              Re-exports the full public API from grr_tool.py
anova            Two-way crossed ANOVA + variance components
capability       Cp / Cpk / Pp / Ppk / Cpm + capability histogram
control_charts   XbarR, XbarS, IMR, PChart, CChart with WE rules 1-4
report           Shared ReportLab PDF building blocks
dashboard        Shared Chart.js HTML building blocks

Quick start
-----------
    from msa_toolkit.grr import load_data, compute_grr
    from msa_toolkit.anova import two_way_anova
    from msa_toolkit.capability import process_capability
    from msa_toolkit.control_charts import XbarR

Regulatory context:  21 CFR 820.72 / AIAG MSA 4th Edition
"""

__version__ = "0.1.0"

from .grr import (
    load_data,
    compute_grr,
    GRRResults,
    build_pdf_report as build_grr_pdf,
    build_dashboard  as build_grr_dashboard,
)
from .anova import (
    AnovaResult,
    two_way_anova,
    variance_components,
    build_anova_pdf,
    build_anova_dashboard,
)
from .capability import (
    CapabilityResult,
    process_capability,
    capability_histogram,
    build_capability_pdf,
    build_capability_dashboard,
)
from .control_charts import (
    XbarR,
    XbarS,
    IMR,
    PChart,
    CChart,
    ControlLimits,
)

__all__ = [
    "__version__",
    "load_data", "compute_grr", "GRRResults",
    "build_grr_pdf", "build_grr_dashboard",
    "AnovaResult", "two_way_anova", "variance_components",
    "build_anova_pdf", "build_anova_dashboard",
    "CapabilityResult", "process_capability", "capability_histogram",
    "build_capability_pdf", "build_capability_dashboard",
    "XbarR", "XbarS", "IMR", "PChart", "CChart", "ControlLimits",
]
