"""Tests for the Claude Code CLI adapter with a mocked subprocess."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dial_system.adapters.base import ProviderError
from app.dial_system.adapters.claude_code import ClaudeCodeAdapter, _build_prompt
from app.models.enums import CrewRole
from app.schemas.dial_system import CompletionRequest, CompletionResult


def _make_request(messages: list[dict[str, str]] | None = None) -> CompletionRequest:
    return CompletionRequest(
        messages=messages or [{"role": "user", "content": "Hello"}],
        role=CrewRole.CAPTAIN,
        max_tokens=100,
        temperature=0.7,
    )


def _result_json(**overrides: Any) -> bytes:
    data: dict[str, Any] = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "Hello from Claude Code!",
        "session_id": "abc",
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_creation_input_tokens": 2,
            "cache_read_input_tokens": 3,
        },
    }
    data.update(overrides)
    return json.dumps(data).encode()


class _FakeStdout:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines

    def __aiter__(self):
        async def _gen():
            for line in self._lines:
                yield line

        return _gen()


class _FakeProcess:
    def __init__(
        self,
        stdout: bytes = b"",
        stderr: bytes = b"",
        returncode: int = 0,
        stream_lines: list[bytes] | None = None,
        hang: bool = False,
    ) -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._hang = hang
        self.killed = False
        self.communicate_input: bytes | None = None

        self.stdin = MagicMock()
        self.stdin.drain = AsyncMock()
        self.stdout = _FakeStdout(stream_lines or [])
        self.stderr = MagicMock()
        self.stderr.read = AsyncMock(return_value=stderr)

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
        if self._hang:
            await asyncio.sleep(60)
        self.communicate_input = input
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        return self.returncode


def _patch_subprocess(monkeypatch: pytest.MonkeyPatch, proc: _FakeProcess) -> dict[str, Any]:
    """Patch create_subprocess_exec; returns a dict capturing the call."""
    captured: dict[str, Any] = {}

    async def fake_exec(*cmd: str, **kwargs: Any) -> _FakeProcess:
        captured["cmd"] = list(cmd)
        captured["kwargs"] = kwargs
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return captured


class TestBuildPrompt:
    def test_single_user_message_passes_through(self) -> None:
        prompt, system = _build_prompt([{"role": "user", "content": "Hello"}])
        assert prompt == "Hello"
        assert system is None

    def test_system_message_folded_into_user_turn(self) -> None:
        # System instructions are folded into the prompt body (not passed via
        # --append-system-prompt, which the CLI's agent prompt overrides), so
        # the returned system is None and the role contract rides in the prompt.
        prompt, system = _build_prompt(
            [
                {"role": "system", "content": "Be brief."},
                {"role": "user", "content": "Hello"},
            ]
        )
        assert system is None
        assert "Be brief." in prompt
        assert "=== INPUT ===" in prompt
        assert "Hello" in prompt
        assert "RESPONSE FORMAT (mandatory)" in prompt

    def test_multi_turn_rendered_as_transcript(self) -> None:
        prompt, _ = _build_prompt(
            [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello!"},
                {"role": "user", "content": "How are you?"},
            ]
        )
        assert prompt == "Human: Hi\n\nAssistant: Hello!\n\nHuman: How are you?"


class TestClaudeCodeAdapter:
    @pytest.mark.asyncio
    async def test_complete_returns_completion_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        proc = _FakeProcess(stdout=_result_json())
        _patch_subprocess(monkeypatch, proc)

        adapter = ClaudeCodeAdapter(model="sonnet")
        result = await adapter.complete(_make_request())

        assert isinstance(result, CompletionResult)
        assert result.content == "Hello from Claude Code!"
        assert result.provider == "claude_code"
        assert result.model == "sonnet"
        # prompt tokens include cache creation + cache read tokens
        assert result.usage.prompt_tokens == 15
        assert result.usage.completion_tokens == 5
        assert result.usage.total_tokens == 20
        assert proc.communicate_input == b"Hello"

    @pytest.mark.asyncio
    async def test_complete_builds_expected_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        proc = _FakeProcess(stdout=_result_json())
        captured = _patch_subprocess(monkeypatch, proc)

        adapter = ClaudeCodeAdapter(
            model="claude-sonnet-4-20250514",
            cli_path="/usr/local/bin/claude",
            max_turns=2,
            extra_args="--permission-mode plan",
        )
        await adapter.complete(
            _make_request(
                [
                    {"role": "system", "content": "Be brief."},
                    {"role": "user", "content": "Hello"},
                ]
            )
        )

        cmd = captured["cmd"]
        assert cmd[0] == "/usr/local/bin/claude"
        assert "--print" in cmd
        assert cmd[cmd.index("--output-format") + 1] == "json"
        assert cmd[cmd.index("--model") + 1] == "claude-sonnet-4-20250514"
        assert cmd[cmd.index("--max-turns") + 1] == "2"
        # Tools disabled; system folded into the user turn (no --append-system-prompt).
        assert cmd[cmd.index("--tools") + 1] == ""
        assert "--append-system-prompt" not in cmd
        assert cmd[-2:] == ["--permission-mode", "plan"]

        # The system instruction reaches the model folded into the stdin prompt.
        folded = proc.communicate_input.decode()
        assert "Be brief." in folded
        assert "Hello" in folded

        env = captured["kwargs"]["env"]
        assert env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "100"

    @pytest.mark.asyncio
    async def test_complete_resolves_model_from_model_usage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        proc = _FakeProcess(
            stdout=_result_json(modelUsage={"claude-sonnet-4-20250514": {"inputTokens": 10}})
        )
        _patch_subprocess(monkeypatch, proc)

        adapter = ClaudeCodeAdapter(model="sonnet")
        result = await adapter.complete(_make_request())

        assert result.model == "claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_complete_raises_provider_error_on_nonzero_exit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        proc = _FakeProcess(stderr=b"boom", returncode=1)
        _patch_subprocess(monkeypatch, proc)

        adapter = ClaudeCodeAdapter(model="sonnet")
        with pytest.raises(ProviderError, match="exited with code 1"):
            await adapter.complete(_make_request())

    @pytest.mark.asyncio
    async def test_complete_marks_rate_limited_from_stderr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        proc = _FakeProcess(stderr=b"API rate limit exceeded", returncode=1)
        _patch_subprocess(monkeypatch, proc)

        adapter = ClaudeCodeAdapter(model="sonnet")
        with pytest.raises(ProviderError):
            await adapter.complete(_make_request())

        assert adapter.check_rate_limit().is_limited is True

    @pytest.mark.asyncio
    async def test_complete_raises_provider_error_on_error_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        proc = _FakeProcess(
            stdout=_result_json(subtype="error_max_turns", is_error=True, result="")
        )
        _patch_subprocess(monkeypatch, proc)

        adapter = ClaudeCodeAdapter(model="sonnet")
        with pytest.raises(ProviderError, match="error_max_turns"):
            await adapter.complete(_make_request())

    @pytest.mark.asyncio
    async def test_complete_raises_provider_error_on_invalid_json(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        proc = _FakeProcess(stdout=b"not json")
        _patch_subprocess(monkeypatch, proc)

        adapter = ClaudeCodeAdapter(model="sonnet")
        with pytest.raises(ProviderError, match="invalid JSON"):
            await adapter.complete(_make_request())

    @pytest.mark.asyncio
    async def test_complete_raises_provider_error_when_cli_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_exec(*cmd: str, **kwargs: Any) -> _FakeProcess:
            raise FileNotFoundError(cmd[0])

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

        adapter = ClaudeCodeAdapter(model="sonnet", cli_path="claude-missing")
        with pytest.raises(ProviderError, match="not found"):
            await adapter.complete(_make_request())

    @pytest.mark.asyncio
    async def test_complete_times_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        proc = _FakeProcess(hang=True)
        _patch_subprocess(monkeypatch, proc)

        adapter = ClaudeCodeAdapter(model="sonnet", timeout_seconds=0)
        with pytest.raises(ProviderError, match="timed out"):
            await adapter.complete(_make_request())

        assert proc.killed is True

    @pytest.mark.asyncio
    async def test_stream_yields_text_from_assistant_events(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lines = [
            json.dumps({"type": "system", "subtype": "init"}).encode(),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "Hello"}]},
                }
            ).encode(),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": " world"}]},
                }
            ).encode(),
            json.dumps(
                {"type": "result", "subtype": "success", "is_error": False, "result": "ignored"}
            ).encode(),
        ]
        proc = _FakeProcess(stream_lines=lines)
        _patch_subprocess(monkeypatch, proc)

        adapter = ClaudeCodeAdapter(model="sonnet")
        tokens = [t async for t in adapter.stream(_make_request())]

        assert tokens == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_stream_falls_back_to_result_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        lines = [
            json.dumps(
                {"type": "result", "subtype": "success", "is_error": False, "result": "Hi!"}
            ).encode(),
        ]
        proc = _FakeProcess(stream_lines=lines)
        _patch_subprocess(monkeypatch, proc)

        adapter = ClaudeCodeAdapter(model="sonnet")
        tokens = [t async for t in adapter.stream(_make_request())]

        assert tokens == ["Hi!"]

    @pytest.mark.asyncio
    async def test_stream_raises_provider_error_on_error_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lines = [
            json.dumps(
                {
                    "type": "result",
                    "subtype": "error_during_execution",
                    "is_error": True,
                    "result": "something broke",
                }
            ).encode(),
        ]
        proc = _FakeProcess(stream_lines=lines)
        _patch_subprocess(monkeypatch, proc)

        adapter = ClaudeCodeAdapter(model="sonnet")
        with pytest.raises(ProviderError, match="error_during_execution"):
            _ = [t async for t in adapter.stream(_make_request())]

    def test_check_rate_limit_not_limited_by_default(self) -> None:
        adapter = ClaudeCodeAdapter(model="sonnet")
        assert adapter.check_rate_limit().is_limited is False
