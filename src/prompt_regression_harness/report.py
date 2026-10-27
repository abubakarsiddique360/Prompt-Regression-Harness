"""Text, markdown and JSON rendering for a run and its diff."""

from __future__ import annotations

from prompt_regression_harness.runner import Diff, RunReport


def status_word(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def render_text(report: RunReport, diff: Diff | None = None) -> str:
    lines = [
        f"{report.suite.name}  -  {len(report.results)} case(s) via {report.provider_name}",
        f"{report.passed_cases} passed, {report.failed_cases} failed  "
        f"({report.pass_rate:.0f}% of cases, {report.passed_checks}/{len(report.checks)} checks)  "
        f"in {report.seconds:.2f}s",
    ]

    for result in report.results:
        if result.passed:
            continue
        lines.append("")
        lines.append(f"{status_word(False)}  {result.case.id}  ({result.seconds:.2f}s)")
        if result.error:
            lines.append(f"      provider error: {result.error}")
            continue
        for index, check in enumerate(result.checks):
            if check.passed:
                continue
            lines.append(f"      check {index + 1} {check.kind:<16}{check.detail}")
        lines.append(f"      response: {_clip(result.response)}")

    if diff is not None:
        lines.append("")
        if diff.clean and not diff.fixes and not diff.new_cases:
            lines.append("Baseline: no regressions")
        else:
            lines.append("Baseline")
            for change in diff.regressions:
                lines.append(f"  REGRESSION  {change.case_id} check {change.check_index + 1} ({change.kind})")
            for change in diff.fixes:
                lines.append(f"  fixed       {change.case_id} check {change.check_index + 1} ({change.kind})")
            if diff.new_cases:
                lines.append(f"  new         {', '.join(diff.new_cases)}")
            if diff.removed_cases:
                lines.append(f"  removed     {', '.join(diff.removed_cases)}")

    return "\n".join(lines)


def _clip(text: str, limit: int = 120) -> str:
    single = " ".join(text.split())
    return single if len(single) <= limit else f"{single[:limit]}..."


def render_markdown(report: RunReport, diff: Diff | None = None) -> str:
    lines = [
        f"# {report.suite.name}",
        "",
        f"**{report.passed_cases}/{len(report.results)} cases passed "
        f"({report.pass_rate:.0f}%) - {report.passed_checks}/{len(report.checks)} checks - "
        f"{report.seconds:.2f}s via `{report.provider_name}`**",
        "",
        "| Case | Tags | Result | Failed checks |",
        "| --- | --- | --- | --- |",
    ]
    for result in report.results:
        failed = ", ".join(check.kind for check in result.failed_checks) or (
            "provider error" if result.error else "-"
        )
        tags = ", ".join(result.case.tags) or "-"
        lines.append(f"| `{result.case.id}` | {tags} | {status_word(result.passed)} | {failed} |")

    summary = report.tag_summary()
    if summary:
        lines += ["", "## By tag", "", "| Tag | Cases | Passed | Rate |", "| --- | --- | --- | --- |"]
        for tag, bucket in summary.items():
            lines.append(f"| {tag} | {int(bucket['cases'])} | {int(bucket['passed'])} | {bucket['rate']:.0f}% |")

    if diff is not None:
        lines += ["", "## Baseline", ""]
        if diff.regressions:
            lines += ["| Case | Check | Kind |", "| --- | --- | --- |"]
            lines += [
                f"| `{change.case_id}` | {change.check_index + 1} | `{change.kind}` |" for change in diff.regressions
            ]
        else:
            lines.append("No regressions.")
        if diff.fixes:
            lines += ["", f"{len(diff.fixes)} check(s) fixed."]
    return "\n".join(lines)
