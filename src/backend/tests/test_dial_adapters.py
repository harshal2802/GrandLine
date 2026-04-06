"""Tests for Dial System provider adapters with mocked SDKs."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dial_system.adapters.anthropic import AnthropicAdapter
from app.dial_system.adapters.ollama import OllamaAdapter
from app.dial_system.adapters.openai import OpenAIAdapter
from app.schemas.dial_system import CompletionRequest, CompletionResult


def _make_request() -> CompletionRequest:
    return CompletionRequest(
        messages=[{"role": "user", "content": "Hello"}],
        max_tokens=100,
        temperature=0.7,
    )


class TestAnthropicAdapter:
    @pytest.mark.asyncio
    async def test_complete_returns_completion_result(self) -> None:
        mock_client = AsyncMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="Hello from Claude!")],
            model="claude-sonnet-4-20250514",
            usage=MagicMock(input_tokens=10, output_tokens=5),
        )

        adapter = AnthropicAdapter(client=mock_client, model="claude-sonnet-4-20250514")
        result = await adapter.complete(_make_request())

        assert isinstance(result, CompletionResult)
        assert result.content == "Hello from Claude!"
        assert result.provider == "anthropic"
        assert result.model == "claude-sonnet-4-20250514"
        assert result.usage.prompt_tokens == 10
        assert result.usage.completion_tokens == 5
        assert result.usage.total_tokens == 15

    @pytest.mark.asyncio
    async def test_complete_calls_sdk_with_correct_params(self) -> None:
        mock_client = AsyncMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="response")],
            model="claude-sonnet-4-20250514",
            usage=MagicMock(input_tokens=5, output_tokens=3),
        )

        adapter = AnthropicAdapter(client=mock_client, model="claude-sonnet-4-20250514")
        request = _make_request()
        await adapter.complete(request)

        mock_client.messages.create.assert_awaited_once_with(
            model="claude-sonnet-4-20250514",
            messages=request.messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )

    @pytest.mark.asyncio
    async def test_stream_yields_tokens(self) -> None:
        mock_client = AsyncMock()

        # Simulate streaming events
        events = [
            MagicMock(type="content_block_delta", delta=MagicMock(type="text_delta", text="Hello")),
            MagicMock(
                type="content_block_delta", delta=MagicMock(type="text_delta", text=" world")
            ),
            MagicMock(type="message_stop"),
        ]

        # messages.stream() returns a context manager (not a coroutine)
        stream_cm = MagicMock()

        async def _aiter(self_inner):
            for e in events:
                yield e

        stream_cm.__aenter__ = AsyncMock(return_value=stream_cm)
        stream_cm.__aexit__ = AsyncMock(return_value=False)
        stream_cm.__aiter__ = _aiter
        # Override messages.stream to be a regular MagicMock returning the context manager
        mock_client.messages.stream = MagicMock(return_value=stream_cm)

        adapter = AnthropicAdapter(client=mock_client, model="claude-sonnet-4-20250514")
        tokens = [t async for t in adapter.stream(_make_request())]

        assert tokens == ["Hello", " world"]

    def test_check_rate_limit_not_limited(self) -> None:
        adapter = AnthropicAdapter(client=AsyncMock(), model="claude-sonnet-4-20250514")
        status = adapter.check_rate_limit()
        assert status.is_limited is False


class TestOpenAIAdapter:
    @pytest.mark.asyncio
    async def test_complete_returns_completion_result(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Hello from GPT!"))],
            model="gpt-4o",
            usage=MagicMock(prompt_tokens=8, completion_tokens=4, total_tokens=12),
        )

        adapter = OpenAIAdapter(client=mock_client, model="gpt-4o")
        result = await adapter.complete(_make_request())

        assert isinstance(result, CompletionResult)
        assert result.content == "Hello from GPT!"
        assert result.provider == "openai"
        assert result.model == "gpt-4o"
        assert result.usage.prompt_tokens == 8
        assert result.usage.completion_tokens == 4
        assert result.usage.total_tokens == 12

    @pytest.mark.asyncio
    async def test_complete_calls_sdk_with_correct_params(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="ok"))],
            model="gpt-4o",
            usage=MagicMock(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

        adapter = OpenAIAdapter(client=mock_client, model="gpt-4o")
        request = _make_request()
        await adapter.complete(request)

        mock_client.chat.completions.create.assert_awaited_once_with(
            model="gpt-4o",
            messages=request.messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )

    @pytest.mark.asyncio
    async def test_stream_yields_tokens(self) -> None:
        mock_client = AsyncMock()

        chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello"))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content=" world"))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content=None))]),
        ]

        async def mock_create(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_client.chat.completions.create.return_value = mock_create()

        adapter = OpenAIAdapter(client=mock_client, model="gpt-4o")
        tokens = [t async for t in adapter.stream(_make_request())]

        assert tokens == ["Hello", " world"]

    def test_check_rate_limit_not_limited(self) -> None:
        adapter = OpenAIAdapter(client=AsyncMock(), model="gpt-4o")
        status = adapter.check_rate_limit()
        assert status.is_limited is False


class TestOllamaAdapter:
    @pytest.mark.asyncio
    async def test_complete_returns_completion_result(self) -> None:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Hello from Ollama!"},
            "model": "llama3",
            "prompt_eval_count": 12,
            "eval_count": 6,
        }
        mock_client.post.return_value = mock_response

        adapter = OllamaAdapter(
            client=mock_client, model="llama3", base_url="http://localhost:11434"
        )
        result = await adapter.complete(_make_request())

        assert isinstance(result, CompletionResult)
        assert result.content == "Hello from Ollama!"
        assert result.provider == "ollama"
        assert result.model == "llama3"
        assert result.usage.prompt_tokens == 12
        assert result.usage.completion_tokens == 6
        assert result.usage.total_tokens == 18

    @pytest.mark.asyncio
    async def test_complete_calls_correct_endpoint(self) -> None:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "ok"},
            "model": "llama3",
            "prompt_eval_count": 1,
            "eval_count": 1,
        }
        mock_client.post.return_value = mock_response

        adapter = OllamaAdapter(
            client=mock_client, model="llama3", base_url="http://localhost:11434"
        )
        request = _make_request()
        await adapter.complete(request)

        mock_client.post.assert_awaited_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://localhost:11434/api/chat"

    @pytest.mark.asyncio
    async def test_stream_yields_tokens(self) -> None:
        mock_client = MagicMock()

        lines = [
            json.dumps({"message": {"content": "Hello"}, "done": False}),
            json.dumps({"message": {"content": " world"}, "done": False}),
            json.dumps({"message": {"content": ""}, "done": True}),
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        # client.stream() returns a sync context manager
        stream_cm = MagicMock()
        stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
        stream_cm.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream.return_value = stream_cm

        adapter = OllamaAdapter(
            client=mock_client, model="llama3", base_url="http://localhost:11434"
        )
        tokens = [t async for t in adapter.stream(_make_request())]

        assert tokens == ["Hello", " world"]

    def test_check_rate_limit_never_limited(self) -> None:
        adapter = OllamaAdapter(
            client=AsyncMock(), model="llama3", base_url="http://localhost:11434"
        )
        status = adapter.check_rate_limit()
        assert status.is_limited is False
