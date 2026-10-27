"""Parse and validate a prompt test suite."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

CHECK_KINDS = (
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
)
VALUE_OPTIONAL = frozenset({"json_object", "refused"})
RESPONSE_FIELDS = ("response", "output", "text")


class SuiteError(ValueError):
    """Raised when a suite document is malformed."""


@dataclass(frozen=True)
class Check:
    kind: str
    value: Any = None
    note: str = ""

    def describe(self) -> str:
        if self.value is None:
            return self.kind
        if isinstance(self.value, list):
            return f"{self.kind}({', '.join(str(item) for item in self.value)})"
        return f"{self.kind}({self.value})"

    def as_dict(self) -> dict:
        return {"kind": self.kind, "value": self.value, "note": self.note}


@dataclass(frozen=True)
class Case:
    id: str
    prompt: str
    checks: tuple[Check, ...]
    tags: tuple[str, ...] = ()
    record: str | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "tags": list(self.tags),
            "checks": [check.as_dict() for check in self.checks],
        }


@dataclass
class Suite:
    name: str
    cases: list[Case] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ids(self) -> list[str]:
        return [case.id for case in self.cases]

    def by_id(self) -> dict[str, Case]:
        return {case.id: case for case in self.cases}

    @property
    def tags(self) -> list[str]:
        found: set[str] = set()
        for case in self.cases:
            found.update(case.tags)
        return sorted(found)


def _text(value: Any, where: str, key: str, required: bool = True) -> str:
    if value is None:
        if required:
            raise SuiteError(f"{where}: '{key}' is required")
        return ""
    if not isinstance(value, str):
        raise SuiteError(f"{where}: '{key}' must be a string")
    return value


def _string_list(value: Any, where: str, key: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SuiteError(f"{where}: '{key}' must be a list of strings")
    return tuple(item for item in value if item)


def _check(raw: Any, where: str) -> Check:
    if not isinstance(raw, dict):
        raise SuiteError(f"{where}: every check must be an object")
    kind = raw.get("kind")
    if not isinstance(kind, str) or kind not in CHECK_KINDS:
        raise SuiteError(f"{where}: unknown check kind {kind!r}, expected one of {', '.join(CHECK_KINDS)}")

    value = raw.get("value")
    if kind not in VALUE_OPTIONAL:
        if value is None:
            raise SuiteError(f"{where}: check '{kind}' needs a 'value'")
        if kind in {"max_chars", "min_chars", "max_words"}:
            if isinstance(value, bool) or not isinstance(value, int):
                raise SuiteError(f"{where}: check '{kind}' needs an integer value")
            if value <= 0:
                raise SuiteError(f"{where}: check '{kind}' needs a positive value")
        elif kind in {"contains", "contains_any", "not_contains", "required_keys"}:
            if isinstance(value, str):
                value = [value]
            if not isinstance(value, list) or not value or any(not isinstance(item, str) for item in value):
                raise SuiteError(f"{where}: check '{kind}' needs a string or a non-empty list of strings")
        elif not isinstance(value, str):
            raise SuiteError(f"{where}: check '{kind}' needs a string value")

    if kind == "refused" and value is not None and not isinstance(value, list):
        value = [value]
    if kind == "refused" and value is not None and any(not isinstance(item, str) for item in value):
        raise SuiteError(f"{where}: check 'refused' needs a list of phrases")

    return Check(kind=kind, value=value, note=_text(raw.get("note"), where, "note", required=False))


def parse_suite(payload: str | dict) -> Suite:
    document: Any = payload
    if isinstance(payload, str):
        try:
            document = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise SuiteError(f"suite is not valid JSON: {exc.msg} at line {exc.lineno}") from exc

    if not isinstance(document, dict):
        raise SuiteError("suite must be a JSON object with a 'cases' list")

    raw_cases = document.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise SuiteError("suite needs a non-empty 'cases' list")

    cases: list[Case] = []
    seen: set[str] = set()
    warnings: list[str] = []
    missing_records: list[str] = []
    for position, raw in enumerate(raw_cases, start=1):
        if not isinstance(raw, dict):
            raise SuiteError(f"case #{position} must be an object")
        case_id = _text(raw.get("id"), f"case #{position}", "id")
        if case_id in seen:
            raise SuiteError(f"duplicate case id '{case_id}'")
        seen.add(case_id)

        prompt = _text(raw.get("prompt"), f"case '{case_id}'", "prompt")

        raw_checks = raw.get("checks")
        if not isinstance(raw_checks, list) or not raw_checks:
            raise SuiteError(f"case '{case_id}' needs a non-empty 'checks' list")
        checks = tuple(_check(item, f"case '{case_id}'") for item in raw_checks)

        record = raw.get("record")
        if record is not None and not isinstance(record, str):
            raise SuiteError(f"case '{case_id}': 'record' must be a string")
        if record is None and not any(isinstance(raw.get(field_name), str) for field_name in RESPONSE_FIELDS):
            missing_records.append(case_id)

        cases.append(
            Case(
                id=case_id,
                prompt=prompt,
                checks=checks,
                tags=_string_list(raw.get("tags"), f"case '{case_id}'", "tags"),
                record=record,
            )
        )

    name = document.get("name")
    if name is not None and not isinstance(name, str):
        raise SuiteError("'name' must be a string")
    if missing_records:
        warnings.append(f"{len(missing_records)} case(s) have no recorded response, the provider will be called")
    return Suite(name=(name or "Prompt suite").strip() or "Prompt suite", cases=cases, warnings=warnings)


def recorded_responses(payload: str | dict) -> dict[str, str]:
    """A fixture file maps case id (or prompt) to a recorded response."""
    document: Any = payload
    if isinstance(payload, str):
        try:
            document = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise SuiteError(f"fixtures are not valid JSON: {exc.msg}") from exc
    if not isinstance(document, dict):
        raise SuiteError("fixtures must be a JSON object of prompt or case id to response")
    fixtures: dict[str, str] = {}
    for key, value in document.items():
        if not isinstance(value, str):
            raise SuiteError(f"fixture '{key}' must be a string")
        fixtures[str(key)] = value
    return fixtures
