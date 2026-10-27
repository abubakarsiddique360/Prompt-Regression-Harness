from __future__ import annotations

import sys

import pytest

from prompt_regression_harness.providers import (
    CommandProvider,
    EchoProvider,
    FixtureProvider,
    Provider,
    ProviderError,
    RecordingProvider,
    split_command,
)


def test_fixture_provider_by_case_id() -> None:
    provider = FixtureProvider({"a": "answer"})
    assert provider.respond("a", "some prompt") == "answer"


def test_fixture_provider_by_prompt() -> None:
    provider = FixtureProvider({"some prompt": "answer"})
    assert provider.respond("unknown", "some prompt") == "answer"


def test_fixture_provider_missing() -> None:
    with pytest.raises(ProviderError, match="no recorded response"):
        FixtureProvider({}).respond("a", "b")


def test_echo_provider_is_deterministic() -> None:
    provider = EchoProvider()
    assert provider.respond("a", "hello") == "You said: hello"
    assert provider.respond("a", "hello") == provider.respond("b", "hello")


def test_recording_provider_keeps_responses() -> None:
    recording = RecordingProvider(inner=EchoProvider())
    recording.respond("a", "hello")
    assert recording.recorded == {"a": "You said: hello"}


def test_provider_protocol() -> None:
    assert isinstance(EchoProvider(), Provider)
    assert isinstance(FixtureProvider({}), Provider)


def test_command_provider_requires_a_placeholder() -> None:
    with pytest.raises(ProviderError, match="must contain"):
        CommandProvider(template="echo hi")


def test_split_command_honours_quotes() -> None:
    assert split_command('python -c "print(1)" {prompt}') == ["python", "-c", "print(1)", "{prompt}"]
    assert split_command("  a   b  ") == ["a", "b"]
    assert split_command('"C:\\Program Files\\python.exe" {prompt}') == ["C:\\Program Files\\python.exe", "{prompt}"]


def test_command_provider_runs_a_program() -> None:
    script = "import sys; print('reply to ' + sys.argv[1].upper())"
    provider = CommandProvider(template=f'{sys.executable} -c "{script}" {{prompt}}')
    assert provider.respond("a", "hello world") == "reply to HELLO WORLD"


def test_command_provider_passes_the_prompt_as_one_argument() -> None:
    script = "import sys; print(len(sys.argv))"
    provider = CommandProvider(template=f'{sys.executable} -c "{script}" {{prompt}}')
    assert provider.respond("a", "two words") == "2"


def test_command_provider_reports_failure() -> None:
    provider = CommandProvider(template=f'{sys.executable} -c "import sys; sys.exit(3)" {{prompt}}')
    with pytest.raises(ProviderError, match="command failed"):
        provider.respond("a", "x")


def test_command_provider_reports_missing_program() -> None:
    provider = CommandProvider(template="definitely-not-a-real-command {prompt}")
    with pytest.raises(ProviderError, match="command not found"):
        provider.respond("a", "x")


def test_command_provider_timeout() -> None:
    script = "import time; time.sleep(5)"
    provider = CommandProvider(template=f'{sys.executable} -c "{script}" {{prompt}}', timeout=0.2)
    with pytest.raises(ProviderError, match="timed out"):
        provider.respond("a", "x")
