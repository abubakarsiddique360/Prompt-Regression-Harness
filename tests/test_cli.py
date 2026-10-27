from __future__ import annotations

import json
from pathlib import Path

from prompt_regression_harness.cli import main

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
SUITE = EXAMPLES / "support-suite.json"
GOOD = EXAMPLES / "recorded.json"
BEFORE = EXAMPLES / "recorded-before-fix.json"


def test_run_passing_suite(capsys) -> None:
    assert main(["run", str(SUITE), "--fixtures", str(GOOD)]) == 0
    out = capsys.readouterr().out
    assert "5 passed, 0 failed" in out
    assert "14/14 checks" in out


def test_run_failing_suite(capsys) -> None:
    assert main(["run", str(SUITE), "--fixtures", str(BEFORE)]) == 1
    out = capsys.readouterr().out
    assert "FAIL  order-status" in out
    assert "contains_any" in out


def test_run_json(capsys) -> None:
    assert main(["run", str(SUITE), "--fixtures", str(GOOD), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["pass_rate"] == 100.0
    assert payload["checks"] == 14


def test_run_markdown(capsys) -> None:
    assert main(["run", str(SUITE), "--fixtures", str(GOOD), "--markdown"]) == 0
    assert "| Case | Tags | Result |" in capsys.readouterr().out


def test_run_with_tag_filter(capsys) -> None:
    assert main(["run", str(SUITE), "--fixtures", str(GOOD), "--tag", "policy"]) == 0
    out = capsys.readouterr().out
    assert "1 case(s)" in out


def test_echo_provider(capsys) -> None:
    assert main(["run", str(SUITE), "--provider", "echo"]) == 1
    assert "via echo" in capsys.readouterr().out


def test_save_and_compare_baseline(tmp_path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    assert main(["run", str(SUITE), "--fixtures", str(GOOD), "--save-baseline", str(baseline)]) == 0
    assert baseline.exists()
    capsys.readouterr()

    assert main(["run", str(SUITE), "--fixtures", str(BEFORE), "--baseline", str(baseline)]) == 1
    out = capsys.readouterr().out
    assert "REGRESSION  order-status check 1" in out


def test_baseline_without_regressions(tmp_path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    main(["run", str(SUITE), "--fixtures", str(GOOD), "--save-baseline", str(baseline)])
    capsys.readouterr()
    assert main(["run", str(SUITE), "--fixtures", str(GOOD), "--baseline", str(baseline)]) == 0
    assert "no regressions" in capsys.readouterr().out


def test_baseline_json_output(tmp_path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    main(["run", str(SUITE), "--fixtures", str(GOOD), "--save-baseline", str(baseline)])
    capsys.readouterr()
    main(["run", str(SUITE), "--fixtures", str(BEFORE), "--baseline", str(baseline), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["diff"]["regressions"][0]["case"] == "order-status"


def test_broken_baseline(tmp_path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{nope}", encoding="utf-8")
    assert main(["run", str(SUITE), "--fixtures", str(GOOD), "--baseline", str(baseline)]) == 2
    assert "not valid JSON" in capsys.readouterr().err


def test_validate(capsys) -> None:
    assert main(["validate", str(SUITE)]) == 0
    assert "5 case(s), 14 check(s)" in capsys.readouterr().out


def test_validate_json(capsys) -> None:
    assert main(["validate", str(SUITE), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["cases"] == 5
    assert "safety" in payload["tags"]


def test_checks_command(capsys) -> None:
    assert main(["checks"]) == 0
    out = capsys.readouterr().out
    assert "contains_any" in out
    assert "json_object" in out


def test_missing_suite(tmp_path, capsys) -> None:
    assert main(["run", str(tmp_path / "nope.json"), "--provider", "echo"]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_invalid_suite(tmp_path, capsys) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"cases": []}', encoding="utf-8")
    assert main(["validate", str(path)]) == 2
    assert "non-empty" in capsys.readouterr().err


def test_fixture_provider_requires_fixtures(capsys) -> None:
    assert main(["run", str(SUITE)]) == 2
    assert "--fixtures is required" in capsys.readouterr().err


def test_command_provider_requires_command(capsys) -> None:
    assert main(["run", str(SUITE), "--provider", "command"]) == 2
    assert "--command is required" in capsys.readouterr().err


def test_missing_fixture_file(tmp_path, capsys) -> None:
    assert main(["run", str(SUITE), "--fixtures", str(tmp_path / "nope.json")]) == 2
    assert "cannot read" in capsys.readouterr().err
