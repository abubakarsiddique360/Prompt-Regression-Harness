"""Command line entry point: run, validate, checks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from prompt_regression_harness.checks import CHECKS
from prompt_regression_harness.models import SuiteError, parse_suite, recorded_responses
from prompt_regression_harness.providers import (
    CommandProvider,
    EchoProvider,
    FixtureProvider,
    ProviderError,
)
from prompt_regression_harness.report import render_markdown, render_text
from prompt_regression_harness.runner import compare, run_suite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prompt-check",
        description="Run a deterministic prompt suite and diff it against a baseline.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="run every case in a suite")
    run_cmd.add_argument("suite")
    run_cmd.add_argument("--provider", choices=["fixture", "echo", "command"], default="fixture")
    run_cmd.add_argument("--fixtures", help="JSON file mapping case id or prompt to a recorded response")
    run_cmd.add_argument("--command", help="shell command template containing {prompt}")
    run_cmd.add_argument("--tag", action="append", default=[], help="only run cases with this tag")
    run_cmd.add_argument("--baseline", help="baseline JSON to compare against")
    run_cmd.add_argument("--save-baseline", help="write the current result as a baseline")
    run_cmd.add_argument("--json", action="store_true")
    run_cmd.add_argument("--markdown", action="store_true")

    validate = sub.add_parser("validate", help="check a suite file without running it")
    validate.add_argument("suite")
    validate.add_argument("--json", action="store_true")

    sub.add_parser("checks", help="list every check kind")
    return parser


def read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise SuiteError(f"cannot read {path}: {exc.strerror or exc}") from exc


def make_provider(args) -> object:
    if args.provider == "echo":
        return EchoProvider()
    if args.provider == "command":
        if not args.command:
            raise ProviderError("--command is required with --provider command")
        return CommandProvider(template=args.command)
    if not args.fixtures:
        raise ProviderError("--fixtures is required with --provider fixture")
    return FixtureProvider(fixtures=recorded_responses(read_text(args.fixtures)))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "checks":
        for spec in CHECKS:
            print(f"{spec.kind:<16}{spec.summary}")
        return 0

    try:
        suite = parse_suite(read_text(args.suite))
    except SuiteError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "validate":
        if args.json:
            payload = {
                "name": suite.name,
                "cases": len(suite.cases),
                "checks": sum(len(case.checks) for case in suite.cases),
                "tags": suite.tags,
                "warnings": suite.warnings,
            }
            print(json.dumps(payload, indent=2))
        else:
            total = sum(len(case.checks) for case in suite.cases)
            print(f"suite is valid: {len(suite.cases)} case(s), {total} check(s), {len(suite.tags)} tag(s)")
            for warning in suite.warnings:
                print(f"  warning: {warning}")
        return 0

    try:
        provider = make_provider(args)
    except (ProviderError, SuiteError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    report = run_suite(suite, provider, only_tags=tuple(args.tag))

    baseline = None
    if args.baseline:
        try:
            baseline = json.loads(read_text(args.baseline))
        except json.JSONDecodeError as exc:
            print(f"error: baseline is not valid JSON: {exc.msg}", file=sys.stderr)
            return 2
        except SuiteError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    diff = compare(report, baseline) if baseline is not None else None

    if args.save_baseline:
        target = Path(args.save_baseline)
        target.write_text(json.dumps(report.baseline(), indent=2) + "\n", encoding="utf-8")

    if args.json:
        payload = report.as_dict()
        if diff is not None:
            payload["diff"] = diff.as_dict()
        print(json.dumps(payload, indent=2))
    elif args.markdown:
        print(render_markdown(report, diff))
    else:
        print(render_text(report, diff))

    if report.failed_cases:
        return 1
    if diff is not None and not diff.clean:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
