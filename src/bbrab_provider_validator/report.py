"""Stable JSON and Markdown report rendering."""

from __future__ import annotations

import html
import json
import re
from typing import Any

from .redact import redact


def json_report(report: dict[str, Any]) -> str:
    return json.dumps(redact(report), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _markdown_escape(value: Any) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value))
    text = html.escape(text, quote=True).replace("`", "&grave;").replace("|", "&vert;")
    return re.sub(r"([\\\[\]{}()*_~#!+.!-])", r"\\\1", text)


def markdown_report(report: dict[str, Any]) -> str:
    safe = redact(report)
    provider = safe.get("provider", {})
    lines = [
        "# Provider validation report",
        "",
        f"- Status: {_markdown_escape(safe.get('status', 'unknown'))}",
        f"- Mode: {_markdown_escape(safe.get('mode', 'unknown'))}",
        f"- Contract: {_markdown_escape(safe.get('contract', 'unknown'))}",
        f"- Provider: {_markdown_escape(provider.get('name', 'unknown'))}",
        f"- Environment: {_markdown_escape(provider.get('environment', 'unknown'))}",
        "",
        "## Checks",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for check in safe.get("checks", []):
        detail = _markdown_escape(json.dumps(check.get("detail"), sort_keys=True, ensure_ascii=False))
        lines.append(
            f"| {_markdown_escape(check.get('name', 'unknown'))} "
            f"| {_markdown_escape(check.get('status', 'unknown'))} | {detail} |"
        )
    lines.extend(["", "> Credentials are referenced by environment-variable name and are never included in this report.", ""])
    return "\n".join(lines)
