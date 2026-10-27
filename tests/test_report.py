from __future__ import annotations

from pathlib import Path

from prompt_regression_harness.models import parse_suite, recorded_responses
from prompt_regression_harness.providers import FixtureProvider
from prompt_regression_harness.report import render_markdown, render_text
from prompt_regression_harness.runner import compare, run_suite

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
SUITE = parse_suite((EXAMPLES / "support-suite.json").read_text(encoding="utf-8"))
GOOD = recorded_responses((EXAMPLES / "recorded.json").read_text(encoding="utf-8"))
BEFORE = recorded_responses((EXAMPLES / "recorded-before-fix.json").read_text(encoding="utf-8"))


def test_text_summary() -> None:
    text = render_text(run_suite(SUITE, FixtureProvider(GOOD)))
    assert "Support assistant suite  -  5 case(s) via fixture" in text
    assert "5 passed, 0 failed" in text
    assert "FAIL" not in text


def test_text_lists_failures_with_detail() -> None:
    text = render_text(run_suite(SUITE, FixtureProvider(BEFORE)))
    assert "FAIL  order-status" in text
    assert "check 1 contains_any" in text
    assert "response: Let me look that up for you." in text


def test_text_shows_provider_errors() -> None:
    text = render_text(run_suite(SUITE, FixtureProvider({})))
    assert "provider error: no recorded response" in text


def test_text_includes_the_diff() -> None:
    baseline = run_suite(SUITE, FixtureProvider(GOOD)).baseline()
    diff = compare(run_suite(SUITE, FixtureProvider(BEFORE)), baseline)
    text = render_text(run_suite(SUITE, FixtureProvider(BEFORE)), diff)
    assert "Baseline" in text
    assert "REGRESSION  order-status check 1 (contains_any)" in text


def test_text_with_clean_baseline() -> None:
    report = run_suite(SUITE, FixtureProvider(GOOD))
    text = render_text(report, compare(report, report.baseline()))
    assert "Baseline: no regressions" in text


def test_text_reports_new_cases() -> None:
    report = run_suite(SUITE, FixtureProvider(GOOD))
    text = render_text(report, compare(report, {"cases": {}}))
    assert "new         greeting" in text


def test_markdown_table() -> None:
    markdown = render_markdown(run_suite(SUITE, FixtureProvider(BEFORE)))
    assert markdown.startswith("# Support assistant suite")
    assert "**4/5 cases passed (80%)" in markdown
    assert "| `order-status` | smoke, orders | FAIL | contains_any |" in markdown
    assert "## By tag" in markdown


def test_markdown_with_diff() -> None:
    baseline = run_suite(SUITE, FixtureProvider(GOOD)).baseline()
    diff = compare(run_suite(SUITE, FixtureProvider(BEFORE)), baseline)
    markdown = render_markdown(run_suite(SUITE, FixtureProvider(BEFORE)), diff)
    assert "## Baseline" in markdown
    assert "| `order-status` | 1 | `contains_any` |" in markdown


def test_markdown_without_regressions() -> None:
    report = run_suite(SUITE, FixtureProvider(GOOD))
    markdown = render_markdown(report, compare(report, report.baseline()))
    assert "No regressions." in markdown


def test_long_responses_are_clipped() -> None:
    suite = parse_suite(
        {
            "cases": [
                {"id": "long", "prompt": "x", "checks": [{"kind": "contains", "value": ["nope"]}]},
            ]
        }
    )
    text = render_text(run_suite(suite, FixtureProvider({"long": "word " * 100})))
    assert "..." in text
