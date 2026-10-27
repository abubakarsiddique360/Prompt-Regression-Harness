"""Execute a suite and compare the result with a stored baseline."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from prompt_regression_harness.checks import CheckResult, evaluate
from prompt_regression_harness.models import Case, Suite
from prompt_regression_harness.providers import Provider, ProviderError

BASELINE_VERSION = 1


@dataclass(frozen=True)
class CaseResult:
    case: Case
    response: str
    checks: tuple[CheckResult, ...]
    error: str = ""
    seconds: float = 0.0

    @property
    def passed(self) -> bool:
        return not self.error and all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> tuple[CheckResult, ...]:
        return tuple(check for check in self.checks if not check.passed)

    def as_dict(self) -> dict:
        return {
            "id": self.case.id,
            "tags": list(self.case.tags),
            "passed": self.passed,
            "error": self.error,
            "seconds": round(self.seconds, 4),
            "checks": [check.as_dict() for check in self.checks],
        }


@dataclass
class RunReport:
    suite: Suite
    provider_name: str
    results: list[CaseResult] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def checks(self) -> list[CheckResult]:
        return [check for result in self.results for check in result.checks]

    @property
    def passed_cases(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def failed_cases(self) -> int:
        return len(self.results) - self.passed_cases

    @property
    def passed_checks(self) -> int:
        return sum(1 for check in self.checks if check.passed)

    @property
    def pass_rate(self) -> float:
        total = len(self.results)
        return self.passed_cases / total * 100.0 if total else 0.0

    def tag_summary(self) -> dict[str, dict[str, float]]:
        summary: dict[str, dict[str, float]] = {}
        for result in self.results:
            for tag in result.case.tags or ("untagged",):
                bucket = summary.setdefault(tag, {"cases": 0, "passed": 0})
                bucket["cases"] += 1
                bucket["passed"] += 1 if result.passed else 0
        for bucket in summary.values():
            bucket["rate"] = bucket["passed"] / bucket["cases"] * 100.0 if bucket["cases"] else 0.0
        return dict(sorted(summary.items()))

    def baseline(self) -> dict:
        return {
            "version": BASELINE_VERSION,
            "suite": self.suite.name,
            "cases": {
                result.case.id: {
                    "passed": result.passed,
                    "checks": [check.passed for check in result.checks],
                }
                for result in self.results
            },
        }

    def as_dict(self) -> dict:
        return {
            "suite": self.suite.name,
            "provider": self.provider_name,
            "cases": len(self.results),
            "passed": self.passed_cases,
            "failed": self.failed_cases,
            "pass_rate": round(self.pass_rate, 1),
            "checks": len(self.checks),
            "passed_checks": self.passed_checks,
            "seconds": round(self.seconds, 3),
            "tags": self.tag_summary(),
            "results": [result.as_dict() for result in self.results],
        }


def run_suite(suite: Suite, provider: Provider, only_tags: tuple[str, ...] = ()) -> RunReport:
    """Run every case; provider failures become failed cases rather than exceptions."""
    selected = [case for case in suite.cases if not only_tags or set(case.tags) & set(only_tags)]
    report = RunReport(suite=suite, provider_name=getattr(provider, "name", "provider"))

    started = time.perf_counter()
    for case in selected:
        case_started = time.perf_counter()
        try:
            response = provider.respond(case.id, case.prompt)
        except ProviderError as exc:
            report.results.append(
                CaseResult(
                    case=case,
                    response="",
                    checks=(),
                    error=str(exc),
                    seconds=time.perf_counter() - case_started,
                )
            )
            continue
        checks = tuple(evaluate(response, check) for check in case.checks)
        report.results.append(
            CaseResult(
                case=case,
                response=response,
                checks=checks,
                seconds=time.perf_counter() - case_started,
            )
        )
    report.seconds = time.perf_counter() - started
    return report


@dataclass(frozen=True)
class Change:
    case_id: str
    check_index: int
    kind: str
    was: bool
    now: bool

    def as_dict(self) -> dict:
        return {
            "case": self.case_id,
            "check": self.check_index,
            "kind": self.kind,
            "was": self.was,
            "now": self.now,
        }


@dataclass
class Diff:
    regressions: list[Change] = field(default_factory=list)
    fixes: list[Change] = field(default_factory=list)
    new_cases: list[str] = field(default_factory=list)
    removed_cases: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.regressions

    def as_dict(self) -> dict:
        return {
            "regressions": [change.as_dict() for change in self.regressions],
            "fixes": [change.as_dict() for change in self.fixes],
            "new_cases": self.new_cases,
            "removed_cases": self.removed_cases,
            "clean": self.clean,
        }


def compare(report: RunReport, baseline: dict) -> Diff:
    """Diff a run against a saved baseline, check by check."""
    previous = baseline.get("cases", {})
    diff = Diff()
    current_ids = {result.case.id for result in report.results}

    for result in report.results:
        saved = previous.get(result.case.id)
        if saved is None:
            diff.new_cases.append(result.case.id)
            continue
        saved_checks = saved.get("checks", [])
        for index, check in enumerate(result.checks):
            was = bool(saved_checks[index]) if index < len(saved_checks) else None
            if was is None:
                continue
            if was and not check.passed:
                diff.regressions.append(Change(result.case.id, index, check.kind, was, check.passed))
            elif not was and check.passed:
                diff.fixes.append(Change(result.case.id, index, check.kind, was, check.passed))

    diff.removed_cases = sorted(set(previous) - current_ids)
    return diff
