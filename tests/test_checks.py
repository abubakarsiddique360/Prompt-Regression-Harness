from __future__ import annotations

import pytest

from prompt_regression_harness.checks import CHECKS, CHECKS_BY_KIND, CheckResult, evaluate
from prompt_regression_harness.models import Check


def result(response: str, kind: str, value=None) -> CheckResult:
    return evaluate(response, Check(kind=kind, value=value))


def test_contains_all_phrases() -> None:
    assert result("Hello there, welcome", "contains", ["hello", "welcome"]).passed is True
    assert result("Hello there", "contains", ["hello", "bye"]).passed is False


def test_contains_any_phrase() -> None:
    assert result("It is in transit", "contains_any", ["shipped", "in transit"]).passed is True
    assert result("Let me check", "contains_any", ["shipped", "in transit"]).passed is False


def test_not_contains() -> None:
    assert result("All good", "not_contains", ["error"]).passed is True
    assert result("There was an ERROR", "not_contains", ["error"]).passed is False


def test_regex_and_not_regex() -> None:
    assert result('{"priority": "high"}', "regex", r'"priority"\s*:\s*"high"').passed is True
    assert result('{"priority": "low"}', "regex", r'"priority"\s*:\s*"high"').passed is False
    assert result("no digits here", "not_regex", r"\d").passed is True
    assert result("card 4111111111111111", "not_regex", r"\b\d{13,19}\b").passed is False


def test_equals_is_trimmed() -> None:
    assert result("  hello\n", "equals", "hello").passed is True
    assert result("hello there", "equals", "hello").passed is False


def test_starts_and_ends_with() -> None:
    assert result("Hello world", "starts_with", "hello").passed is True
    assert result("Hello world", "starts_with", "world").passed is False
    assert result("Hello world", "ends_with", "world").passed is True
    assert result("Hello world", "ends_with", "hello").passed is False


def test_length_bounds() -> None:
    assert result("abc", "max_chars", 3).passed is True
    assert result("abcd", "max_chars", 3).passed is False
    assert result("abc", "min_chars", 3).passed is True
    assert result("ab", "min_chars", 3).passed is False
    assert result("one two", "max_words", 2).passed is True
    assert result("one two three", "max_words", 2).passed is False


def test_json_object() -> None:
    assert result('{"a": 1}', "json_object").passed is True
    assert result("not json", "json_object").passed is False
    assert result('["a"]', "json_object").passed is False


def test_json_object_accepts_fenced_blocks() -> None:
    fenced = '```json\n{"title": "x", "priority": "high"}\n```'
    assert result(fenced, "json_object").passed is True


def test_required_keys() -> None:
    assert result('{"title": "x", "priority": "high"}', "required_keys", ["title", "priority"]).passed is True
    outcome = result('{"title": "x"}', "required_keys", ["title", "priority"])
    assert outcome.passed is False
    assert "priority" in outcome.detail


def test_required_keys_needs_json() -> None:
    outcome = result("plain text", "required_keys", ["title"])
    assert outcome.passed is False
    assert "invalid JSON" in outcome.detail


def test_refused_default_phrases() -> None:
    assert result("I cannot help with that request.", "refused").passed is True
    assert result("Sure, here is the number.", "refused").passed is False


def test_refused_with_custom_phrases() -> None:
    assert result("Please contact support.", "refused", ["contact support"]).passed is True
    assert result("Anything else?", "refused", ["contact support"]).passed is False


def test_unknown_kind_fails_gracefully() -> None:
    outcome = evaluate("anything", Check(kind="mystery"))
    assert outcome.passed is False
    assert outcome.detail == "unknown check kind"


def test_registry_is_consistent() -> None:
    assert len(CHECKS_BY_KIND) == len(CHECKS)
    assert all(spec.summary for spec in CHECKS)
    assert set(CHECKS_BY_KIND) == {
        "contains",
        "contains_any",
        "not_contains",
        "regex",
        "not_regex",
        "equals",
        "starts_with",
        "ends_with",
        "max_chars",
        "min_chars",
        "max_words",
        "json_object",
        "required_keys",
        "refused",
    }


def test_result_dict() -> None:
    assert result("abc", "max_chars", 10).as_dict() == {
        "kind": "max_chars",
        "passed": True,
        "detail": "3 of 10 characters",
    }


@pytest.mark.parametrize(
    ("response", "kind", "value"),
    [
        ("", "min_chars", 1),
        ("x", "max_chars", 0),
    ],
)
def test_edge_inputs(response: str, kind: str, value: int) -> None:
    assert result(response, kind, value).passed is False
