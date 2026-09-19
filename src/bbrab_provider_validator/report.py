"""Stable JSON and Markdown report rendering."""

from __future__ import annotations

import json
from typing import Any

from .redact import redact


def json_report(report: dict[str, Any]) -> str:
    return json.dumps(redact(report), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def markdown_report(report: dict[str, Any]) -> str:
    safe = redact(report)
    provider = safe.get("provider", {})
    lines = [
        "# Provider validation report",
        "",
        f"- Status: **{safe.get('status', 'unknown')}**",
        f"- Mode: `{safe.get('mode', 'unknown')}`",
        f"- Contract: `{safe.get('contract', 'unknown')}`",
        f"- Provider: {provider.get('name', 'unknown')}",
        f"- Environment: `{provider.get('environment', 'unknown')}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for check in safe.get("checks", []):
        detail = json.dumps(check.get("detail"), sort_keys=True, ensure_ascii=False).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{check.get('name')}` | {check.get('status')} | `{detail}` |")
    lines.extend(["", "> Credentials are referenced by environment-variable name and are never included in this report.", ""])
    return "\n".join(lines)
