"""
tests/test_attribute_dashboard.py
==================================
Verifies `--attribute --dashboard` on grr_tool.py writes a self-contained
HTML file with the per-operator Kappa chart (attribute-agreement analysis
had console/JSON output only; this exercises the new dashboard path).
"""

import csv
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
GRR_TOOL  = REPO_ROOT / "grr_tool.py"


def _write_attribute_csv(path: Path) -> None:
    rows = [["Part", "Operator", "Trial1", "Trial2"]]
    truth = {f"P{i}": i % 2 for i in range(1, 11)}
    for part, base in truth.items():
        for op, flip_rate in [("Alice", 0), ("Bob", 1), ("Carol", 2)]:
            v1 = base if (hash((part, op, 1)) % 5) >= flip_rate else 1 - base
            v2 = base if (hash((part, op, 2)) % 5) >= flip_rate else 1 - base
            rows.append([part, op, v1, v2])
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(rows)


def test_attribute_dashboard_via_cli(tmp_path):
    csv_path  = tmp_path / "attribute.csv"
    html_path = tmp_path / "attr_dashboard.html"
    _write_attribute_csv(csv_path)

    result = subprocess.run(
        [
            sys.executable, str(GRR_TOOL),
            "--attribute",
            "--input", str(csv_path),
            "--dashboard", str(html_path),
            "--equipment", "Go/No-Go Gauge",
            "--operator", "QA Team",
            "--title", "Unit Test Attribute Study",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, f"CLI failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    assert html_path.exists(), "Attribute dashboard HTML was not created"

    html = html_path.read_text(encoding="utf-8")
    assert "Kappa by Operator" in html
    assert "kappaThresholds" in html
    assert "Alice" in html and "Bob" in html and "Carol" in html
