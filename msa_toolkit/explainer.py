"""
msa_toolkit.explainer
======================
Turns a GR&R JSON summary (same shape as grr_tool.py's --json export)
into a short plain-English narrative using the Claude API: an executive
summary, likely root causes, and recommended next actions.

Requires ANTHROPIC_API_KEY. If it isn't set, or the `anthropic` package
isn't installed, generate_narrative() prints a notice and returns None
so callers can treat --explain as best-effort and never fail report
generation because of it.
"""

from __future__ import annotations

import json
import os
from typing import Optional

PROMPT_TEMPLATE = """You are a measurement systems analysis (MSA) expert helping a quality \
engineer interpret a Gauge R&R study, per AIAG MSA 4th Edition methodology.

Study summary (JSON):
{payload}

Write a short narrative report with three sections:
1. Executive Summary -- one plain-English paragraph, no statistics jargon.
2. Likely Root Causes -- if status is MARGINAL or UNACCEPTABLE, name the most \
probable physical causes (operator technique, gauge wear, fixturing, part \
variation, etc.) based on which component is driving the failure. If \
ACCEPTABLE, note what's worth continuing to monitor.
3. Recommended Next Actions -- 2 to 4 concrete, prioritized actions a quality \
engineer could take this week.

Keep the whole report under 300 words. Reference the numbers naturally in \
prose rather than repeating the raw JSON."""


def generate_narrative(payload: dict, model: str = "claude-sonnet-5") -> Optional[str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[!] --explain skipped: ANTHROPIC_API_KEY is not set.")
        return None
    try:
        import anthropic
    except ImportError:
        print("[!] --explain skipped: run `pip install anthropic` to enable narrative reports.")
        return None

    client = anthropic.Anthropic(api_key=api_key)
    prompt = PROMPT_TEMPLATE.format(payload=json.dumps(payload, indent=2, default=str))
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
