"""
msa_toolkit.__main__
====================
Entry point for ``python -m msa_toolkit``.

Sub-commands
------------
grr          (default) Full GR&R analysis — same behaviour as grr_tool.py
anova        Two-way crossed ANOVA with variance components
capability   Process capability indices (Cp/Cpk/Pp/Ppk/Cpm)
chart        SPC control charts (xbar-r, xbar-s, i-mr, p, c)

Usage examples
--------------
    python -m msa_toolkit sample_grr.csv         # GRR shortcut (default)
    python -m msa_toolkit grr --input data.csv --output report.pdf

    python -m msa_toolkit anova --input data.csv --output anova.pdf
    python -m msa_toolkit anova --input data.csv --dashboard anova.html

    python -m msa_toolkit capability --input data.csv --lsl 9.95 --usl 10.05
    python -m msa_toolkit capability --input data.csv --lsl 9.95 --usl 10.05 \\
        --output cap.pdf --dashboard cap.html --target 10.0

    python -m msa_toolkit chart --type xbar-r --input data.csv --subgroup 5
    python -m msa_toolkit chart --type i-mr   --input data.csv
    python -m msa_toolkit chart --type p      --input defect_data.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------

def _cmd_grr(args: argparse.Namespace) -> None:
    """Delegate to grr_tool.main() after reconstructing sys.argv."""
    import grr_tool

    # Reconstruct argv that grr_tool.parse_args() expects
    argv = ["grr_tool.py", "--input", str(args.input)]
    if args.output:
        argv += ["--output", str(args.output)]
    if getattr(args, "dashboard", None):
        argv += ["--dashboard", str(args.dashboard)]
    if getattr(args, "tolerance", None) is not None:
        argv += ["--tolerance", str(args.tolerance)]
    if getattr(args, "title", None):
        argv += ["--title", args.title]
    if getattr(args, "equipment", None):
        argv += ["--equipment", args.equipment]
    if getattr(args, "operator", None):
        argv += ["--operator", args.operator]
    if getattr(args, "generate_sample", False):
        argv.append("--generate-sample")

    sys.argv = argv
    grr_tool.main()


def _cmd_anova(args: argparse.Namespace) -> None:
    """Run two-way ANOVA on a CSV with Part, Operator, Measurement columns."""
    import pandas as pd
    from msa_toolkit.anova import (
        two_way_anova, variance_components,
        print_anova_table, build_anova_pdf, build_anova_dashboard,
    )

    csv_path = Path(args.input)
    if not csv_path.exists():
        print(f"[ERROR] Input file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(csv_path)
    result = two_way_anova(df)
    print_anova_table(result)

    if args.output:
        build_anova_pdf(
            result, Path(args.output),
            equipment=getattr(args, "equipment", "Unspecified"),
            study_operator=getattr(args, "operator", "Quality Engineering"),
            title=getattr(args, "title", "Two-Way ANOVA Report"),
        )
    if getattr(args, "dashboard", None):
        build_anova_dashboard(
            result, Path(args.dashboard),
            equipment=getattr(args, "equipment", "Unspecified"),
            study_operator=getattr(args, "operator", "Quality Engineering"),
            title=getattr(args, "title", "ANOVA Dashboard"),
        )


def _cmd_capability(args: argparse.Namespace) -> None:
    """Compute process capability from a flat Measurement column CSV."""
    import numpy as np
    import pandas as pd
    from msa_toolkit.capability import (
        process_capability, print_capability_summary,
        build_capability_pdf, build_capability_dashboard,
    )

    csv_path = Path(args.input)
    if not csv_path.exists():
        print(f"[ERROR] Input file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(csv_path)
    result = process_capability(
        df,
        lsl=args.lsl,
        usl=args.usl,
        target=getattr(args, "target", None),
        subgroup_size=getattr(args, "subgroup", None),
    )
    print_capability_summary(result)

    if args.output:
        build_capability_pdf(
            df, result, Path(args.output),
            characteristic=getattr(args, "characteristic", "Measurement"),
            study_operator=getattr(args, "operator", "Quality Engineering"),
            title=getattr(args, "title", "Process Capability Report"),
        )
    if getattr(args, "dashboard", None):
        build_capability_dashboard(
            result, Path(args.dashboard),
            characteristic=getattr(args, "characteristic", "Measurement"),
            study_operator=getattr(args, "operator", "Quality Engineering"),
            title=getattr(args, "title", "Capability Dashboard"),
        )


def _cmd_chart(args: argparse.Namespace) -> None:
    """Generate a control chart from CSV data."""
    import pandas as pd
    from msa_toolkit.control_charts import XbarR, XbarS, IMR, PChart, CChart

    csv_path = Path(args.input)
    if not csv_path.exists():
        print(f"[ERROR] Input file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(csv_path)
    chart_type = args.type.lower().replace("_", "-")

    if chart_type == "xbar-r":
        n = args.subgroup
        if n is None:
            print("[ERROR] --subgroup is required for xbar-r", file=sys.stderr)
            sys.exit(1)
        chart = XbarR(subgroup_size=n).fit(df)
    elif chart_type == "xbar-s":
        n = args.subgroup
        if n is None:
            print("[ERROR] --subgroup is required for xbar-s", file=sys.stderr)
            sys.exit(1)
        chart = XbarS(subgroup_size=n).fit(df)
    elif chart_type in ("i-mr", "imr", "i_mr"):
        chart = IMR().fit(df)
    elif chart_type == "p":
        chart = PChart().fit(df)
    elif chart_type == "c":
        chart = CChart().fit(df)
    else:
        print(f"[ERROR] Unknown chart type '{args.type}'. "
              "Choose from: xbar-r, xbar-s, i-mr, p, c", file=sys.stderr)
        sys.exit(1)

    print(f"[+] {chart._chart_type} fitted.")

    title = getattr(args, "title", None) or chart._chart_type
    equipment = getattr(args, "equipment", "Unspecified")
    operator  = getattr(args, "operator", "Quality Engineering")

    if args.output:
        chart.to_pdf(Path(args.output), title=title, equipment=equipment,
                     study_operator=operator)
    if getattr(args, "dashboard", None):
        chart.to_html(Path(args.dashboard), title=title, equipment=equipment,
                      study_operator=operator)
    if not args.output and not getattr(args, "dashboard", None):
        # No output requested — show a quick matplotlib window if interactive,
        # otherwise save a PNG next to the input file.
        png_path = csv_path.with_name(csv_path.stem + f"_{chart_type.replace('-','_')}.png")
        fig = chart.plot()
        fig.savefig(png_path, dpi=150, bbox_inches="tight")
        import matplotlib.pyplot as plt
        plt.close(fig)
        print(f"[+] Chart saved to: {png_path}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="python -m msa_toolkit",
        description=(
            "msa_toolkit — MSA / SPC toolkit for medical device manufacturing.\n"
            "Sub-commands: grr, anova, capability, chart\n"
            "Omitting a sub-command defaults to grr (backward-compatible)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    root.add_argument("--version", action="version",
                      version="msa_toolkit 0.1.0  (grr_tool compatible)")
    subs = root.add_subparsers(dest="command")

    # ── grr sub-command ────────────────────────────────────────────────────
    grr_p = subs.add_parser("grr", help="GR&R analysis (AIAG MSA 4th Ed.)")
    grr_p.add_argument("--input", "-i",  type=str, required=True)
    grr_p.add_argument("--output", "-o", type=str, default=None)
    grr_p.add_argument("--dashboard", "-d", type=str, default=None)
    grr_p.add_argument("--tolerance", "-t", type=float, default=None)
    grr_p.add_argument("--title",     type=str, default="GR&R Study Report")
    grr_p.add_argument("--equipment", "-e", type=str, default="Unspecified Gage")
    grr_p.add_argument("--operator",  type=str, default="Quality Engineering")
    grr_p.add_argument("--generate-sample", dest="generate_sample",
                       action="store_true")

    # ── anova sub-command ──────────────────────────────────────────────────
    anova_p = subs.add_parser("anova", help="Two-way crossed ANOVA")
    anova_p.add_argument("--input", "-i",  type=str, required=True)
    anova_p.add_argument("--output", "-o", type=str, default=None)
    anova_p.add_argument("--dashboard", "-d", type=str, default=None)
    anova_p.add_argument("--title",     type=str, default="Two-Way ANOVA Report")
    anova_p.add_argument("--equipment", "-e", type=str, default="Unspecified")
    anova_p.add_argument("--operator",  type=str, default="Quality Engineering")

    # ── capability sub-command ─────────────────────────────────────────────
    cap_p = subs.add_parser("capability", help="Process capability indices")
    cap_p.add_argument("--input", "-i",  type=str, required=True)
    cap_p.add_argument("--lsl",  type=float, required=True)
    cap_p.add_argument("--usl",  type=float, required=True)
    cap_p.add_argument("--target",   type=float, default=None)
    cap_p.add_argument("--subgroup", type=int,   default=None)
    cap_p.add_argument("--output",   "-o", type=str, default=None)
    cap_p.add_argument("--dashboard","-d", type=str, default=None)
    cap_p.add_argument("--title",    type=str, default="Process Capability Report")
    cap_p.add_argument("--characteristic", type=str, default="Measurement")
    cap_p.add_argument("--operator", type=str, default="Quality Engineering")

    # ── chart sub-command ──────────────────────────────────────────────────
    chart_p = subs.add_parser("chart", help="SPC control charts")
    chart_p.add_argument("--type", "-t", type=str, required=True,
                         choices=["xbar-r", "xbar-s", "i-mr", "p", "c"],
                         metavar="TYPE",
                         help="Chart type: xbar-r | xbar-s | i-mr | p | c")
    chart_p.add_argument("--input",    "-i", type=str, required=True)
    chart_p.add_argument("--subgroup", "-n", type=int, default=None)
    chart_p.add_argument("--output",   "-o", type=str, default=None)
    chart_p.add_argument("--dashboard","-d", type=str, default=None)
    chart_p.add_argument("--title",    type=str, default=None)
    chart_p.add_argument("--equipment","-e", type=str, default="Unspecified")
    chart_p.add_argument("--operator", type=str, default="Quality Engineering")

    return root


def main() -> None:
    """Main entry point for ``python -m msa_toolkit``."""
    # If the first argument is a .csv file or positional, treat as grr shortcut
    if len(sys.argv) >= 2 and sys.argv[1].endswith(".csv"):
        sys.argv.insert(1, "grr")
        sys.argv.insert(2, "--input")

    parser = _build_parser()
    args   = parser.parse_args()

    if args.command is None or args.command == "grr":
        _cmd_grr(args)
    elif args.command == "anova":
        _cmd_anova(args)
    elif args.command == "capability":
        _cmd_capability(args)
    elif args.command == "chart":
        _cmd_chart(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
