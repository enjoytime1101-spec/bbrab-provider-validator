"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import ConfigurationError, load_json
from .report import json_report, markdown_report
from .validator import validate_fixture, validate_live


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bbrab-provider-validator")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="run the acceptance contract")
    validate.add_argument("--config", required=True, help="path to a secret-free JSON configuration")
    source = validate.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", help="path to a recorded, secret-free fixture")
    source.add_argument("--live", action="store_true", help="make real provider requests")
    validate.add_argument("--acknowledge-provider-cost", action="store_true", help="required safety acknowledgement for live mode")
    validate.add_argument("--timeout", type=float, default=15.0)
    validate.add_argument("--format", choices=("json", "markdown"), default="json")
    validate.add_argument("--report-json")
    validate.add_argument("--report-markdown")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = load_json(args.config)
        if args.fixture:
            if args.acknowledge_provider_cost:
                raise ConfigurationError("--acknowledge-provider-cost is only meaningful with --live")
            report = validate_fixture(config, load_json(args.fixture))
        else:
            report = validate_live(
                config,
                live=args.live,
                acknowledge_provider_cost=args.acknowledge_provider_cost,
                timeout=args.timeout,
            )
        rendered_json = json_report(report)
        rendered_markdown = markdown_report(report)
        if args.report_json:
            Path(args.report_json).write_text(rendered_json, encoding="utf-8")
        if args.report_markdown:
            Path(args.report_markdown).write_text(rendered_markdown, encoding="utf-8")
        sys.stdout.write(rendered_json if args.format == "json" else rendered_markdown)
        return 0 if report["status"] == "passed" else 1
    except (ConfigurationError, PermissionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (ValueError, OSError):
        print("error: invalid input or output", file=sys.stderr)
        return 2
    except Exception:
        print("error: validation failed safely", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
