"""Tests for Dial System adapter factory."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.dial_system.adapters.anthropic import AnthropicAdapter
from app.dial_system.adapters.claude_code import ClaudeCodeAdapter
from app.dial_system.adapters.ollama import OllamaAdapter
from app.dial_system.adapters.openai import OpenAIAdapter
from app.dial_system.factory import (
    _default_model_for,
    _resolve_fallback_entry,
    build_router_from_config,
    create_adapter,
)
from app.models.dial_config import DialConfig
from app.models.enums import CrewRole

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

    def test_creates_claude_code_adapter(self) -> None:
        adapter = create_adapter("claude_code", "sonnet", _make_settings())
        assert isinstance(adapter, ClaudeCodeAdapter)

    def test_creates_claude_code_adapter_with_dash_alias(self) -> None:
        adapter = create_adapter("claude-code", "sonnet", _make_settings())
        assert isinstance(adapter, ClaudeCodeAdapter)

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


class TestResolveFallbackEntry:
    def test_object_form_uses_explicit_model(self) -> None:
        provider, model = _resolve_fallback_entry(
            {"provider": "openai", "model": "gpt-4o-mini"}, _make_settings()
        )
        assert (provider, model) == ("openai", "gpt-4o-mini")

    def test_bare_string_resolves_to_provider_default(self) -> None:
        provider, model = _resolve_fallback_entry("openai", _make_settings())
        assert provider == "openai"
        assert model == "gpt-4o"

    def test_object_form_without_model_uses_provider_default(self) -> None:
        provider, model = _resolve_fallback_entry({"provider": "ollama"}, _make_settings())
        assert (provider, model) == ("ollama", "llama3")

    def test_default_model_for_configured_provider_uses_settings(self) -> None:
        settings = Settings(
            anthropic_api_key="k",
            openai_api_key="k",
            dial_default_provider="anthropic",
            dial_default_model="claude-custom-9",
        )
        assert _default_model_for("anthropic", settings) == "claude-custom-9"

    def test_unknown_fallback_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="No default model known"):
            _resolve_fallback_entry("gemini", _make_settings())

    def test_invalid_entry_shape_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid fallback entry"):
            _resolve_fallback_entry(123, _make_settings())

    def test_object_form_missing_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="missing 'provider'"):
            _resolve_fallback_entry({"model": "gpt-4o"}, _make_settings())


class TestCrossVendorFailoverModel:
    """Regression for #50: fallbacks must not reuse the primary's model id."""

    def test_fallback_adapter_uses_its_own_model_not_primary(self) -> None:
        config = DialConfig(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            role_mapping={
                "captain": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
            },
            fallback_chain={"captain": [{"provider": "openai", "model": "gpt-4o"}]},
        )

        router = build_router_from_config(config, _make_settings(), MagicMock(), MagicMock())

        fallback = router._fallback_chains[CrewRole.CAPTAIN][0]
        assert isinstance(fallback, OpenAIAdapter)
        assert fallback._model == "gpt-4o"
        assert fallback._model != "claude-sonnet-4-20250514"

    def test_bare_string_fallback_does_not_inherit_primary_model(self) -> None:
        config = DialConfig(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            role_mapping={
                "captain": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
            },
            fallback_chain={"captain": ["openai"]},
        )

        router = build_router_from_config(config, _make_settings(), MagicMock(), MagicMock())

        fallback = router._fallback_chains[CrewRole.CAPTAIN][0]
        assert isinstance(fallback, OpenAIAdapter)
        assert fallback._model == "gpt-4o"
