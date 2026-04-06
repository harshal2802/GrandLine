"""Tests for Dial System adapter factory."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.dial_system.adapters.anthropic import AnthropicAdapter
from app.dial_system.adapters.ollama import OllamaAdapter
from app.dial_system.adapters.openai import OpenAIAdapter
from app.dial_system.factory import build_router_from_config, create_adapter
from app.models.dial_config import DialConfig

VOYAGE_ID = uuid.uuid4()


def _make_settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        openai_api_key="test-key",
        ollama_base_url="http://localhost:11434",
    )


class TestCreateAdapter:
    def test_creates_anthropic_adapter(self) -> None:
        adapter = create_adapter("anthropic", "claude-sonnet-4-20250514", _make_settings())
        assert isinstance(adapter, AnthropicAdapter)

    def test_creates_openai_adapter(self) -> None:
        adapter = create_adapter("openai", "gpt-4o", _make_settings())
        assert isinstance(adapter, OpenAIAdapter)

    def test_creates_ollama_adapter(self) -> None:
        adapter = create_adapter("ollama", "llama3", _make_settings())
        assert isinstance(adapter, OllamaAdapter)

    def test_raises_for_unknown_provider(self) -> None:
        with pytest.raises(ValueError, match="Unknown provider"):
            create_adapter("gemini", "gemini-pro", _make_settings())


class TestBuildRouterFromConfig:
    def test_builds_router_from_valid_config(self) -> None:
        config = DialConfig(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            role_mapping={
                "captain": {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-20250514",
                },
                "navigator": {"provider": "openai", "model": "gpt-4o"},
            },
            fallback_chain={"captain": ["openai", "ollama"]},
        )
        mushi = MagicMock()
        rate_limiter = MagicMock()

        router = build_router_from_config(config, _make_settings(), mushi, rate_limiter)

        assert router is not None

    def test_raises_for_missing_provider_key(self) -> None:
        config = DialConfig(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            role_mapping={"captain": {"model": "claude-sonnet-4-20250514"}},
            fallback_chain=None,
        )

        with pytest.raises(ValueError, match="Missing 'provider' or 'model'"):
            build_router_from_config(config, _make_settings(), MagicMock(), MagicMock())

    def test_raises_for_missing_model_key(self) -> None:
        config = DialConfig(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            role_mapping={"captain": {"provider": "anthropic"}},
            fallback_chain=None,
        )

        with pytest.raises(ValueError, match="Missing 'provider' or 'model'"):
            build_router_from_config(config, _make_settings(), MagicMock(), MagicMock())

    def test_raises_for_unknown_provider_in_mapping(self) -> None:
        config = DialConfig(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            role_mapping={
                "captain": {"provider": "gemini", "model": "gemini-pro"},
            },
            fallback_chain=None,
        )

        with pytest.raises(ValueError, match="Unknown provider"):
            build_router_from_config(config, _make_settings(), MagicMock(), MagicMock())

    def test_handles_none_fallback_chain(self) -> None:
        config = DialConfig(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            role_mapping={
                "captain": {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-20250514",
                },
            },
            fallback_chain=None,
        )

        router = build_router_from_config(config, _make_settings(), MagicMock(), MagicMock())
        assert router is not None
