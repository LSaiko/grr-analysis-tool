"""
tests/test_json_export.py
==========================
Verifies the `--json` CLI flag on grr_tool.py: it should write a
machine-readable GR&R summary (schema_version, metadata, and metrics)
alongside (or instead of) the PDF/HTML outputs, for downstream tools
(e.g. the foremode pFMEA generator) to consume.

Runs the actual CLI as a subprocess against the sample-data generator
already built into grr_tool.py (`generate_sample_data`), rather than
importing internals, so the test also exercises the argparse wiring.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
GRR_TOOL  = REPO_ROOT / "grr_tool.py"


def test_json_export_via_cli(tmp_path):
    csv_path  = tmp_path / "sample.csv"
    json_path = tmp_path / "summary.json"

    result = subprocess.run(
        [
            sys.executable, str(GRR_TOOL),
            "--generate-sample",
            "--input", str(csv_path),
            "--json", str(json_path),
            "--equipment", "Test Caliper",
            "--operator", "QA Tester",
            "--title", "Unit Test GR&R",
            "--tolerance", "0.05",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, f"CLI failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    assert json_path.exists(), "JSON summary file was not created"

    with open(json_path) as f:
        data = json.load(f)

    assert data["schema_version"] == 1
    assert data["equipment"] == "Test Caliper"
    assert data["operator"] == "QA Tester"
    assert data["characteristic"] == "Unit Test GR&R"
    assert data["tolerance"] == 0.05

    metrics = data["metrics"]
    assert isinstance(metrics["ndc"], int)
    assert metrics["status"] in ("ACCEPTABLE", "MARGINAL", "UNACCEPTABLE")
    assert "grr" in metrics and "ev" in metrics and "av" in metrics
