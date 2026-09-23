"""
tests/test_test_evidence.py
===========================
--test-evidence: emits a traceability-matrix-dhf TestEvidence record that
validates against schemas/test-evidence.schema.json, and leaves the PDF
report byte-identical (reportlab invariant mode pins timestamps/IDs).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from grr_tool import GRRResults, build_test_evidence

REPO_ROOT = Path(__file__).parent.parent
SCHEMA = json.loads((REPO_ROOT / "schemas" / "test-evidence.schema.json").read_text())


def run_cli(*args):
    env = {**os.environ, "RL_invariant": "1"}
    out = subprocess.run([sys.executable, str(REPO_ROOT / "grr_tool.py"), *map(str, args)],
                         cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return out


@pytest.mark.parametrize("csv_name,result", [
    ("sample_grr_acceptable.csv", "pass"),
    ("sample_grr.csv", "conditional"),
    ("sample_grr_unacceptable.csv", "fail"),
])
def test_evidence_validates_and_pdf_unchanged(tmp_path, csv_name, result):
    csv_path = REPO_ROOT / csv_name
    plain_pdf, pdf, ev = tmp_path / "plain.pdf", tmp_path / "report.pdf", tmp_path / "ev.json"

    run_cli("--input", csv_path, "--output", plain_pdf)
    run_cli("--input", csv_path, "--output", pdf, "--test-evidence", ev,
            "--requirement-ids", "REQ-12, REQ-14")

    evidence = json.loads(ev.read_text())
    jsonschema.validate(evidence, SCHEMA, format_checker=jsonschema.FormatChecker())
    assert evidence["type"] == "GRR"
    assert evidence["source_repo"] == "grr-analysis-tool"
    assert evidence["result"] == result
    assert evidence["linked_requirement_ids"] == ["REQ-12", "REQ-14"]
    assert evidence["evidence_uri"] == pdf.resolve().as_uri()
    assert pdf.read_bytes() == plain_pdf.read_bytes()


def test_acceptable_with_low_ndc_is_conditional(tmp_path):
    csv_path = tmp_path / "x.csv"
    csv_path.write_text("x")
    res = GRRResults(status="ACCEPTABLE", ndc=4)
    ev = build_test_evidence(res, csv_path, tmp_path / "r.pdf", [])
    assert ev["result"] == "conditional"
    jsonschema.validate(ev, SCHEMA)


def test_evidence_requires_pdf(tmp_path):
    out = subprocess.run(
        [sys.executable, str(REPO_ROOT / "grr_tool.py"), "--input", str(REPO_ROOT / "sample_grr.csv"),
         "--dashboard", str(tmp_path / "d.html"), "--test-evidence", str(tmp_path / "ev.json")],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
    assert out.returncode != 0 and "--test-evidence needs a PDF" in out.stderr
