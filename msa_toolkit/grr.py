"""
msa_toolkit.grr
===============
Re-exports every public symbol from ``grr_tool.py`` (the Prior
Invention at the repository root) without duplicating any logic.

``grr_tool.py`` is left completely unmodified; this module simply
makes its API available under the ``msa_toolkit`` namespace so callers
can write::

    from msa_toolkit.grr import compute_grr, GRRResults

instead of reaching for the root-level module directly.

The sys.path insertion is idempotent and only touches the repo root —
no global state is altered for other imports.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the repository root (containing grr_tool.py) is on sys.path
# ---------------------------------------------------------------------------
_REPO_ROOT = str(Path(__file__).parent.parent.resolve())
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ---------------------------------------------------------------------------
# Re-export the full public API from grr_tool
# ---------------------------------------------------------------------------
from grr_tool import (  # noqa: E402
    __version__ as grr_tool_version,
    MeasurementRecord,
    OperatorStats,
    GRRResults,
    K1_BY_TRIALS,
    K2_BY_OPERATORS,
    K3_BY_PARTS,
    D4_BY_TRIALS,
    GRR_ACCEPTABLE_THRESHOLD,
    GRR_MARGINAL_THRESHOLD,
    NDC_MINIMUM,
    generate_sample_data,
    load_data,
    compute_grr,
    print_console_report,
    build_pdf_report,
    build_dashboard,
)

__all__ = [
    "grr_tool_version",
    "MeasurementRecord",
    "OperatorStats",
    "GRRResults",
    "K1_BY_TRIALS",
    "K2_BY_OPERATORS",
    "K3_BY_PARTS",
    "D4_BY_TRIALS",
    "GRR_ACCEPTABLE_THRESHOLD",
    "GRR_MARGINAL_THRESHOLD",
    "NDC_MINIMUM",
    "generate_sample_data",
    "load_data",
    "compute_grr",
    "print_console_report",
    "build_pdf_report",
    "build_dashboard",
]
