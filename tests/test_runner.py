from __future__ import annotations

from pathlib import Path

import pytest

from prompt_regression_harness.models import parse_suite, recorded_responses
from prompt_regression_harness.providers import FixtureProvider, ProviderError
from prompt_regression_harness.runner import compare, run_suite

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
SUITE = parse_suite((EXAMPLES / "support-suite.json").read_text(encoding="utf-8"))
GOOD = recorded_responses((EXAMPLES / "recorded.json").read_text(encoding="utf-8"))
BEFORE = recorded_responses((EXAMPLES / "recorded-before-fix.json").read_text(encoding="utf-8"))


def test_all_cases_pass() -> None:
    report = run_suite(SUITE, FixtureProvider(GOOD))
    assert report.passed_cases == 5
    assert report.failed_cases == 0
    assert report.pass_rate == 100.0
    assert report.passed_checks == len(report.checks) == 14


def test_a_regression_is_a_failed_case() -> None:
    report = run_suite(SUITE, FixtureProvider(BEFORE))
    assert report.passed_cases == 4
    assert report.failed_cases == 1
    assert report.pass_rate == 80.0
    failing = next(result for result in report.results if not result.passed)
    assert failing.case.id == "order-status"
    assert failing.failed_checks[0].kind == "contains_any"


def test_tag_filter() -> None:
    report = run_suite(SUITE, FixtureProvider(GOOD), only_tags=("smoke",))
    assert {result.case.id for result in report.results} == {"greeting", "order-status"}


def test_tag_filter_without_matches() -> None:
    report = run_suite(SUITE, FixtureProvider(GOOD), only_tags=("nope",))
    assert report.results == []
    assert report.pass_rate == 0.0


def test_provider_error_becomes_a_failed_case() -> None:
    report = run_suite(SUITE, FixtureProvider({}))
    assert report.failed_cases == 5
    assert all("no recorded response" in result.error for result in report.results)


class BrokenProvider:
    name = "broken"

    def respond(self, case_id: str, prompt: str) -> str:
        raise ProviderError("boom")


def test_provider_exception_is_recorded() -> None:
    report = run_suite(SUITE, BrokenProvider())
    assert report.failed_cases == 5
    assert report.results[0].error == "boom"


def test_tag_summary() -> None:
    summary = run_suite(SUITE, FixtureProvider(BEFORE)).tag_summary()
    assert summary["smoke"] == {"cases": 2, "passed": 1, "rate": 50.0}
    assert summary["safety"]["rate"] == 100.0


def test_untagged_cases_are_grouped() -> None:
    suite = parse_suite({"cases": [{"id": "a", "prompt": "x", "checks": [{"kind": "json_object"}]}]})
    summary = run_suite(suite, FixtureProvider({"a": "{}"})).tag_summary()
    assert "untagged" in summary


def test_baseline_round_trip() -> None:
    report = run_suite(SUITE, FixtureProvider(GOOD))
    baseline = report.baseline()
    assert baseline["version"] == 1
    assert baseline["cases"]["greeting"]["passed"] is True
    assert len(baseline["cases"]["greeting"]["checks"]) == 3


def test_compare_finds_regressions() -> None:
    baseline = run_suite(SUITE, FixtureProvider(GOOD)).baseline()
    diff = compare(run_suite(SUITE, FixtureProvider(BEFORE)), baseline)
    assert len(diff.regressions) == 1
    change = diff.regressions[0]
    assert change.case_id == "order-status"
    assert change.check_index == 0
    assert change.kind == "contains_any"
    assert diff.clean is False


def test_compare_finds_fixes() -> None:
    baseline = run_suite(SUITE, FixtureProvider(BEFORE)).baseline()
    diff = compare(run_suite(SUITE, FixtureProvider(GOOD)), baseline)
    assert len(diff.fixes) == 1
    assert diff.fixes[0].case_id == "order-status"
    assert diff.clean is True


def test_compare_with_identical_runs() -> None:
    report = run_suite(SUITE, FixtureProvider(GOOD))
    diff = compare(report, report.baseline())
    assert diff.regressions == []
    assert diff.fixes == []


def test_compare_new_and_removed_cases() -> None:
    suite = parse_suite({"cases": [{"id": "only", "prompt": "x", "checks": [{"kind": "json_object"}]}]})
    baseline = {"cases": {"gone": {"passed": True, "checks": [True]}}}
    diff = compare(run_suite(suite, FixtureProvider({"only": "{}"})), baseline)
    assert diff.new_cases == ["only"]
    assert diff.removed_cases == ["gone"]


def test_report_dict_shape() -> None:
    payload = run_suite(SUITE, FixtureProvider(GOOD)).as_dict()
    assert payload["suite"] == "Support assistant suite"
    assert payload["provider"] == "fixture"
    assert payload["cases"] == 5
    assert payload["pass_rate"] == 100.0
    assert payload["results"][0]["checks"][0]["passed"] is True


def test_diff_dict_shape() -> None:
    baseline = run_suite(SUITE, FixtureProvider(GOOD)).baseline()
    payload = compare(run_suite(SUITE, FixtureProvider(BEFORE)), baseline).as_dict()
    assert payload["clean"] is False
    assert payload["regressions"][0]["case"] == "order-status"


@pytest.mark.parametrize("case", SUITE.cases, ids=SUITE.ids)
def test_every_case_has_checks(case) -> None:
    assert case.checks
    assert case.prompt
