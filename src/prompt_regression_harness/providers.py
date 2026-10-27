"""Response providers: recorded fixtures, a deterministic echo, or a shell command."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class ProviderError(RuntimeError):
    """Raised when a provider cannot produce a response."""


@runtime_checkable
class Provider(Protocol):
    name: str

    def respond(self, case_id: str, prompt: str) -> str: ...


@dataclass
class FixtureProvider:
    """Replay recorded model output, which makes a suite fully offline and repeatable."""

    fixtures: dict[str, str]
    name: str = "fixture"

    def respond(self, case_id: str, prompt: str) -> str:
        if case_id in self.fixtures:
            return self.fixtures[case_id]
        if prompt in self.fixtures:
            return self.fixtures[prompt]
        raise ProviderError(f"no recorded response for case '{case_id}'")


@dataclass
class EchoProvider:
    """Deterministic stand in for a model: echoes the prompt with a fixed prefix."""

    prefix: str = "You said: "
    name: str = "echo"

    def respond(self, case_id: str, prompt: str) -> str:
        return f"{self.prefix}{prompt}"


def split_command(template: str) -> list[str]:
    """Split a command template on spaces, honouring double quotes.

    Backslashes are preserved so Windows paths keep working, and `{prompt}` is
    substituted after splitting so a prompt containing spaces stays one argument.
    """
    tokens: list[str] = []
    current: list[str] = []
    quoted = False
    for character in template:
        if character == '"':
            quoted = not quoted
            continue
        if character.isspace() and not quoted:
            if current:
                tokens.append("".join(current))
                current = []
            continue
        current.append(character)
    if current:
        tokens.append("".join(current))
    return tokens


@dataclass
class CommandProvider:
    """Run a CLI and use its standard output as the response.

    The template must contain `{prompt}`; the prompt is passed as a single argument,
    never through a shell, so quotes and newlines are safe.
    """

    template: str
    timeout: float = 60.0
    name: str = "command"

    def __post_init__(self) -> None:
        if "{prompt}" not in self.template:
            raise ProviderError("the command template must contain {prompt}")

    def respond(self, case_id: str, prompt: str) -> str:
        parts = [part.replace("{prompt}", prompt) for part in split_command(self.template)]
        if not parts:
            raise ProviderError("the command template is empty")
        try:
            completed = subprocess.run(
                parts,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ProviderError(f"command not found: {parts[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(f"command timed out after {self.timeout:g}s") from exc
        if completed.returncode != 0:
            message = (completed.stderr or "").strip().splitlines()
            detail = message[0] if message else f"exit code {completed.returncode}"
            raise ProviderError(f"command failed: {detail}")
        return completed.stdout.strip()


@dataclass
class RecordingProvider:
    """Wrap another provider and keep every response, so a run can be used as a baseline."""

    inner: Provider
    recorded: dict[str, str] = field(default_factory=dict)
    name: str = "record"

    def respond(self, case_id: str, prompt: str) -> str:
        response = self.inner.respond(case_id, prompt)
        self.recorded[case_id] = response
        return response
