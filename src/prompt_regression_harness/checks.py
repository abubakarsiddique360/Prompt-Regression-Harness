"""The check catalogue: one small deterministic assertion per kind."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from prompt_regression_harness.models import Check

DEFAULT_REFUSAL_PHRASES = (
    "i can't",
    "i cannot",
    "i won't",
    "i will not",
    "unable to help",
    "not able to help",
    "cannot help with that",
    "can't help with that",
)


@dataclass(frozen=True)
class CheckResult:
    kind: str
    passed: bool
    detail: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class CheckSpec:
    kind: str
    summary: str
    runner: Callable[[str, Any], tuple[bool, str]]


def _as_list(value: Any) -> list[str]:
    return [value] if isinstance(value, str) else list(value or [])


def _contains(response: str, value: Any) -> tuple[bool, str]:
    items = _as_list(value)
    lowered = response.lower()
    missing = [item for item in items if item.lower() not in lowered]
    if missing:
        return False, f"missing: {', '.join(missing)}"
    return True, f"found all {len(items)} phrase(s)"


def _contains_any(response: str, value: Any) -> tuple[bool, str]:
    items = _as_list(value)
    lowered = response.lower()
    found = [item for item in items if item.lower() in lowered]
    if not found:
        return False, f"none of: {', '.join(items)}"
    return True, f"found '{found[0]}'"


def _not_contains(response: str, value: Any) -> tuple[bool, str]:
    items = _as_list(value)
    lowered = response.lower()
    present = [item for item in items if item.lower() in lowered]
    if present:
        return False, f"should not mention: {', '.join(present)}"
    return True, f"none of {len(items)} forbidden phrase(s) present"


def _regex(response: str, value: Any) -> tuple[bool, str]:
    match = re.search(str(value), response, re.MULTILINE)
    if not match:
        return False, f"pattern /{value}/ did not match"
    return True, f"matched '{match.group(0)[:40]}'"


def _not_regex(response: str, value: Any) -> tuple[bool, str]:
    match = re.search(str(value), response, re.MULTILINE)
    if match:
        return False, f"pattern /{value}/ matched '{match.group(0)[:40]}'"
    return True, f"pattern /{value}/ absent"


def _equals(response: str, value: Any) -> tuple[bool, str]:
    if response.strip() == str(value).strip():
        return True, "exact match"
    return False, "response differs from the expected text"


def _starts_with(response: str, value: Any) -> tuple[bool, str]:
    if response.strip().lower().startswith(str(value).lower()):
        return True, f"starts with '{value}'"
    return False, f"does not start with '{value}'"


def _ends_with(response: str, value: Any) -> tuple[bool, str]:
    if response.strip().lower().endswith(str(value).lower()):
        return True, f"ends with '{value}'"
    return False, f"does not end with '{value}'"


def _max_chars(response: str, value: Any) -> tuple[bool, str]:
    if len(response) <= value:
        return True, f"{len(response)} of {value} characters"
    return False, f"{len(response)} characters, limit is {value}"


def _min_chars(response: str, value: Any) -> tuple[bool, str]:
    if len(response) >= value:
        return True, f"{len(response)} of {value} characters"
    return False, f"only {len(response)} characters, minimum is {value}"


def _max_words(response: str, value: Any) -> tuple[bool, str]:
    words = len(response.split())
    if words <= value:
        return True, f"{words} of {value} words"
    return False, f"{words} words, limit is {value}"


def _load_json(response: str) -> tuple[Any, str]:
    text = response.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text), ""
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc.msg}"


def _json_object(response: str, _value: Any) -> tuple[bool, str]:
    payload, problem = _load_json(response)
    if problem:
        return False, problem
    if not isinstance(payload, dict):
        return False, f"expected an object, found {type(payload).__name__}"
    return True, f"object with {len(payload)} key(s)"


def _required_keys(response: str, value: Any) -> tuple[bool, str]:
    payload, problem = _load_json(response)
    if problem:
        return False, problem
    if not isinstance(payload, dict):
        return False, f"expected an object, found {type(payload).__name__}"
    missing = [key for key in _as_list(value) if key not in payload]
    if missing:
        return False, f"missing key(s): {', '.join(missing)}"
    return True, "all keys present"


def _refused(response: str, value: Any) -> tuple[bool, str]:
    phrases = _as_list(value) if value else list(DEFAULT_REFUSAL_PHRASES)
    lowered = response.lower()
    found = [phrase for phrase in phrases if phrase.lower() in lowered]
    if found:
        return True, f"refused with '{found[0]}'"
    return False, "the response does not read as a refusal"


CHECKS: tuple[CheckSpec, ...] = (
    CheckSpec("contains", "All listed phrases appear, case insensitive.", _contains),
    CheckSpec("contains_any", "At least one listed phrase appears.", _contains_any),
    CheckSpec("not_contains", "None of the listed phrases appear.", _not_contains),
    CheckSpec("regex", "The pattern matches somewhere in the response.", _regex),
    CheckSpec("not_regex", "The pattern does not match anywhere.", _not_regex),
    CheckSpec("equals", "The trimmed response equals the value exactly.", _equals),
    CheckSpec("starts_with", "The trimmed response starts with the value.", _starts_with),
    CheckSpec("ends_with", "The trimmed response ends with the value.", _ends_with),
    CheckSpec("max_chars", "The response is at most this many characters.", _max_chars),
    CheckSpec("min_chars", "The response is at least this many characters.", _min_chars),
    CheckSpec("max_words", "The response is at most this many words.", _max_words),
    CheckSpec("json_object", "The response parses as a JSON object (code fences allowed).", _json_object),
    CheckSpec("required_keys", "The JSON object contains every listed key.", _required_keys),
    CheckSpec("refused", "The response reads as a refusal.", _refused),
)

CHECKS_BY_KIND = {spec.kind: spec for spec in CHECKS}


def evaluate(response: str, check: Check) -> CheckResult:
    spec = CHECKS_BY_KIND.get(check.kind)
    if spec is None:
        return CheckResult(kind=check.kind, passed=False, detail="unknown check kind")
    passed, detail = spec.runner(response, check.value)
    return CheckResult(kind=check.kind, passed=passed, detail=detail)
