from __future__ import annotations

import json
from pathlib import Path

import pytest

from prompt_regression_harness.models import SuiteError, parse_suite, recorded_responses

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

BASIC = {
    "name": "Basic",
    "cases": [
        {"id": "a", "prompt": "hello", "checks": [{"kind": "contains", "value": "hi"}]},
    ],
}


def test_parses_suite() -> None:
    suite = parse_suite(BASIC)
    assert suite.name == "Basic"
    assert suite.ids == ["a"]
    assert suite.cases[0].checks[0].kind == "contains"


def test_default_name() -> None:
    payload = dict(BASIC)
    payload.pop("name")
    assert parse_suite(payload).name == "Prompt suite"


def test_tags_are_collected() -> None:
    payload = {
        "cases": [
            {"id": "a", "prompt": "x", "checks": [{"kind": "json_object"}], "tags": ["smoke", "safety"]},
            {"id": "b", "prompt": "y", "checks": [{"kind": "json_object"}], "tags": ["safety"]},
        ]
    }
    assert parse_suite(payload).tags == ["safety", "smoke"]


def test_value_is_normalised_to_a_list() -> None:
    suite = parse_suite({"cases": [{"id": "a", "prompt": "x", "checks": [{"kind": "contains", "value": "hi"}]}]})
    assert suite.cases[0].checks[0].value == ["hi"]


@pytest.mark.parametrize(
    "payload",
    [
        "{broken",
        [],
        {"cases": []},
        {"cases": "x"},
        {"cases": [{"prompt": "x", "checks": [{"kind": "json_object"}]}]},
        {"cases": [{"id": "a", "prompt": "x"}]},
        {"cases": [{"id": "a", "prompt": "x", "checks": []}]},
        {"cases": [{"id": "a", "prompt": "x", "checks": [{"kind": "nope", "value": "y"}]}]},
        {"cases": [{"id": "a", "prompt": "x", "checks": [{"kind": "contains"}]}]},
        {"cases": [{"id": "a", "prompt": "x", "checks": [{"kind": "max_chars", "value": 0}]}]},
        {"cases": [{"id": "a", "prompt": "x", "checks": [{"kind": "max_chars", "value": "5"}]}]},
        {"cases": [{"id": "a", "prompt": "x", "checks": [{"kind": "contains", "value": []}]}]},
        {"cases": [{"id": "a", "prompt": "x", "checks": [{"kind": "regex", "value": 5}]}]},
        {"cases": [{"id": "a", "prompt": "x", "tags": "smoke", "checks": [{"kind": "json_object"}]}]},
        {"cases": [{"id": "a", "prompt": "x", "record": 5, "checks": [{"kind": "json_object"}]}]},
        {"cases": [{"id": "a", "prompt": "x", "checks": ["contains"]}]},
        {
            "cases": [
                {"id": "a", "prompt": "x", "checks": [{"kind": "json_object"}]},
                {"id": "a", "prompt": "y", "checks": [{"kind": "json_object"}]},
            ]
        },
        {"name": 5, "cases": [{"id": "a", "prompt": "x", "checks": [{"kind": "json_object"}]}]},
    ],
)
def test_invalid_suites(payload) -> None:
    with pytest.raises(SuiteError):
        parse_suite(payload)


def test_warning_when_there_is_no_recorded_response() -> None:
    suite = parse_suite({"cases": [{"id": "a", "prompt": "x", "checks": [{"kind": "json_object"}]}]})
    assert "no recorded response" in suite.warnings[0]


def test_recorded_response_silences_the_warning() -> None:
    suite = parse_suite({"cases": [{"id": "a", "prompt": "x", "record": "{}", "checks": [{"kind": "json_object"}]}]})
    assert suite.warnings == []
    assert suite.cases[0].record == "{}"


def test_example_suite_is_valid() -> None:
    suite = parse_suite((EXAMPLES / "support-suite.json").read_text(encoding="utf-8"))
    assert suite.name == "Support assistant suite"
    assert len(suite.cases) == 5
    assert sum(len(case.checks) for case in suite.cases) == 14
    assert suite.tags == ["orders", "policy", "safety", "smoke", "structured"]


def test_check_describe() -> None:
    suite = parse_suite(BASIC)
    assert suite.cases[0].checks[0].describe() == "contains(hi)"


def test_check_describe_without_value() -> None:
    suite = parse_suite({"cases": [{"id": "a", "prompt": "x", "checks": [{"kind": "json_object"}]}]})
    assert suite.cases[0].checks[0].describe() == "json_object"


def test_case_dict() -> None:
    payload = parse_suite(BASIC).cases[0].as_dict()
    assert payload["id"] == "a"
    assert payload["checks"][0] == {"kind": "contains", "value": ["hi"], "note": ""}


def test_recorded_responses() -> None:
    fixtures = recorded_responses((EXAMPLES / "recorded.json").read_text(encoding="utf-8"))
    assert set(fixtures) == {"greeting", "refund-window", "ticket-json", "card-data", "order-status"}


@pytest.mark.parametrize("payload", ["{no", "[]", {"a": 5}])
def test_invalid_fixtures(payload) -> None:
    with pytest.raises(SuiteError):
        recorded_responses(payload)


def test_fixture_file_is_json() -> None:
    payload = json.loads((EXAMPLES / "recorded.json").read_text(encoding="utf-8"))
    assert all(isinstance(value, str) for value in payload.values())
