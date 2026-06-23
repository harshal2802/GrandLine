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


class TestClaudeCodePerRoleMaxTurns:
    """Phase C1: per-role claude_code max_turns from the role mapping."""

    def test_create_adapter_uses_role_max_turns(self) -> None:
        adapter = create_adapter(
            "claude_code",
            "sonnet",
            _make_settings(),
            role_cfg={"provider": "claude_code", "model": "sonnet", "max_turns": 7},
        )
        assert isinstance(adapter, ClaudeCodeAdapter)
        assert adapter._max_turns == 7

    def test_create_adapter_falls_back_to_settings_when_no_role_cfg(self) -> None:
        settings = _make_settings()
        adapter = create_adapter("claude_code", "sonnet", settings)
        assert isinstance(adapter, ClaudeCodeAdapter)
        assert adapter._max_turns == settings.claude_code_max_turns

    def test_create_adapter_falls_back_when_role_cfg_has_no_max_turns(self) -> None:
        settings = _make_settings()
        adapter = create_adapter(
            "claude_code",
            "sonnet",
            settings,
            role_cfg={"provider": "claude_code", "model": "sonnet"},
        )
        assert isinstance(adapter, ClaudeCodeAdapter)
        assert adapter._max_turns == settings.claude_code_max_turns

    def test_create_adapter_falls_back_when_role_max_turns_invalid(self) -> None:
        settings = _make_settings()
        adapter = create_adapter(
            "claude_code",
            "sonnet",
            settings,
            role_cfg={"provider": "claude_code", "model": "sonnet", "max_turns": 99},
        )
        assert isinstance(adapter, ClaudeCodeAdapter)
        assert adapter._max_turns == settings.claude_code_max_turns

    def test_build_router_threads_role_max_turns_into_adapter(self) -> None:
        config = DialConfig(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            role_mapping={
                "shipwright": {
                    "provider": "claude_code",
                    "model": "sonnet",
                    "max_turns": 3,
                },
            },
            fallback_chain=None,
        )

        router = build_router_from_config(config, _make_settings(), MagicMock(), MagicMock())

        adapter = router._role_mapping[CrewRole.SHIPWRIGHT]
        assert isinstance(adapter, ClaudeCodeAdapter)
        assert adapter._max_turns == 3

    def test_build_router_claude_code_without_max_turns_uses_settings(self) -> None:
        settings = _make_settings()
        config = DialConfig(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            role_mapping={
                "shipwright": {"provider": "claude_code", "model": "sonnet"},
            },
            fallback_chain=None,
        )

        router = build_router_from_config(config, settings, MagicMock(), MagicMock())

        adapter = router._role_mapping[CrewRole.SHIPWRIGHT]
        assert isinstance(adapter, ClaudeCodeAdapter)
        assert adapter._max_turns == settings.claude_code_max_turns

    def test_non_claude_code_role_cfg_ignored(self) -> None:
        # A non-claude_code provider must be unaffected by a max_turns key.
        adapter = create_adapter(
            "anthropic",
            "claude-sonnet-4-20250514",
            _make_settings(),
            role_cfg={"provider": "anthropic", "model": "x", "max_turns": 5},
        )
        assert isinstance(adapter, AnthropicAdapter)


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


class TestPerUserClaudeCodeToken:
    """Phase C0: thread a per-user CLAUDE_CODE_OAUTH_TOKEN into claude_code adapters."""

    def test_create_adapter_passes_oauth_token(self) -> None:
        adapter = create_adapter(
            "claude_code", "sonnet", _make_settings(), oauth_token="sk-ant-user"
        )
        assert isinstance(adapter, ClaudeCodeAdapter)
        assert adapter._oauth_token == "sk-ant-user"

    def test_create_adapter_default_oauth_token_none(self) -> None:
        adapter = create_adapter("claude_code", "sonnet", _make_settings())
        assert isinstance(adapter, ClaudeCodeAdapter)
        assert adapter._oauth_token is None

    def test_build_router_threads_token_into_claude_code_role(self) -> None:
        config = DialConfig(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            role_mapping={
                "shipwright": {"provider": "claude_code", "model": "sonnet"},
                "captain": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
            },
            fallback_chain={"shipwright": [{"provider": "claude_code", "model": "sonnet"}]},
        )
        router = build_router_from_config(
            config,
            _make_settings(),
            MagicMock(),
            MagicMock(),
            claude_code_oauth_token="sk-ant-user",
        )
        primary = router._role_mapping[CrewRole.SHIPWRIGHT]
        assert isinstance(primary, ClaudeCodeAdapter)
        assert primary._oauth_token == "sk-ant-user"
        # Non claude_code roles are never given the token.
        assert not isinstance(router._role_mapping[CrewRole.CAPTAIN], ClaudeCodeAdapter)
        # The claude_code fallback also runs as the user.
        fb = router._fallback_chains[CrewRole.SHIPWRIGHT][0]
        assert isinstance(fb, ClaudeCodeAdapter)
        assert fb._oauth_token == "sk-ant-user"

    def test_build_router_without_token_leaves_host_behavior(self) -> None:
        config = DialConfig(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            role_mapping={"shipwright": {"provider": "claude_code", "model": "sonnet"}},
            fallback_chain=None,
        )
        router = build_router_from_config(config, _make_settings(), MagicMock(), MagicMock())
        adapter = router._role_mapping[CrewRole.SHIPWRIGHT]
        assert isinstance(adapter, ClaudeCodeAdapter)
        assert adapter._oauth_token is None
