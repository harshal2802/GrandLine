"""Tests for DialConfig shipwright sub-schema and resolver."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.dial_config import (
    DialConfigCreate,
    DialConfigUpdate,
    ShipwrightRoleConfig,
    resolve_shipwright_max_concurrency,
    validate_fallback_chain,
)


class TestShipwrightRoleConfig:
    def test_accepts_none(self) -> None:
        cfg = ShipwrightRoleConfig(max_concurrency=None)
        assert cfg.max_concurrency is None

    def test_accepts_default(self) -> None:
        cfg = ShipwrightRoleConfig()
        assert cfg.max_concurrency is None

    def test_accepts_one(self) -> None:
        cfg = ShipwrightRoleConfig(max_concurrency=1)
        assert cfg.max_concurrency == 1

    def test_accepts_ten(self) -> None:
        cfg = ShipwrightRoleConfig(max_concurrency=10)
        assert cfg.max_concurrency == 10

    def test_rejects_zero(self) -> None:
        with pytest.raises(ValidationError):
            ShipwrightRoleConfig(max_concurrency=0)

    def test_rejects_eleven(self) -> None:
        with pytest.raises(ValidationError):
            ShipwrightRoleConfig(max_concurrency=11)

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValidationError):
            ShipwrightRoleConfig(max_concurrency=-1)

    def test_rejects_string(self) -> None:
        with pytest.raises(ValidationError):
            ShipwrightRoleConfig(max_concurrency="3")  # type: ignore[arg-type]


class TestResolveShipwrightMaxConcurrency:
    def test_returns_1_when_role_mapping_is_none(self) -> None:
        assert resolve_shipwright_max_concurrency(None) == 1

    def test_returns_1_when_shipwright_key_missing(self) -> None:
        assert resolve_shipwright_max_concurrency({"captain": {}}) == 1

    def test_returns_1_when_shipwright_is_not_a_dict(self) -> None:
        assert resolve_shipwright_max_concurrency({"shipwright": "claude"}) == 1

    def test_returns_1_when_shipwright_is_list(self) -> None:
        assert resolve_shipwright_max_concurrency({"shipwright": [1, 2, 3]}) == 1

    def test_returns_value_when_valid(self) -> None:
        role_mapping: dict[str, Any] = {"shipwright": {"max_concurrency": 4}}
        assert resolve_shipwright_max_concurrency(role_mapping) == 4

    def test_returns_1_when_max_concurrency_is_zero(self) -> None:
        assert resolve_shipwright_max_concurrency({"shipwright": {"max_concurrency": 0}}) == 1

    def test_returns_1_when_max_concurrency_too_large(self) -> None:
        assert resolve_shipwright_max_concurrency({"shipwright": {"max_concurrency": 99}}) == 1

    def test_returns_1_when_max_concurrency_negative(self) -> None:
        assert resolve_shipwright_max_concurrency({"shipwright": {"max_concurrency": -5}}) == 1

    def test_returns_1_when_max_concurrency_is_string(self) -> None:
        assert resolve_shipwright_max_concurrency({"shipwright": {"max_concurrency": "3"}}) == 1

    def test_returns_1_when_max_concurrency_absent(self) -> None:
        assert resolve_shipwright_max_concurrency({"shipwright": {}}) == 1

    def test_returns_1_when_max_concurrency_is_none_value(self) -> None:
        assert resolve_shipwright_max_concurrency({"shipwright": {"max_concurrency": None}}) == 1

    def test_ignores_other_keys_in_shipwright_config(self) -> None:
        role_mapping: dict[str, Any] = {
            "shipwright": {"max_concurrency": 5, "model": "claude-sonnet-4"}
        }
        assert resolve_shipwright_max_concurrency(role_mapping) == 5


class TestValidateFallbackChain:
    def test_none_passes(self) -> None:
        assert validate_fallback_chain(None) is None

    def test_bare_string_entries_pass(self) -> None:
        chain: dict[str, Any] = {"captain": ["openai", "ollama"]}
        assert validate_fallback_chain(chain) == chain

    def test_object_entries_pass(self) -> None:
        chain: dict[str, Any] = {
            "captain": [{"provider": "openai", "model": "gpt-4o"}],
        }
        assert validate_fallback_chain(chain) == chain

    def test_mixed_entries_pass(self) -> None:
        chain: dict[str, Any] = {
            "captain": ["ollama", {"provider": "openai", "model": "gpt-4o"}],
        }
        assert validate_fallback_chain(chain) == chain

    def test_unknown_provider_string_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported provider 'gemini'"):
            validate_fallback_chain({"captain": ["gemini"]})

    def test_unknown_provider_object_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported provider 'gemini'"):
            validate_fallback_chain({"captain": [{"provider": "gemini", "model": "x"}]})

    def test_object_missing_provider_rejected(self) -> None:
        with pytest.raises(ValueError, match="missing 'provider'"):
            validate_fallback_chain({"captain": [{"model": "gpt-4o"}]})

    def test_non_list_entries_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be a list"):
            validate_fallback_chain({"captain": "openai"})

    def test_invalid_entry_type_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be a provider string"):
            validate_fallback_chain({"captain": [123]})

    def test_dial_config_create_validates_fallback_chain(self) -> None:
        import uuid

        with pytest.raises(ValidationError):
            DialConfigCreate(
                voyage_id=uuid.uuid4(),
                role_mapping={"captain": {"provider": "anthropic", "model": "x"}},
                fallback_chain={"captain": ["gemini"]},
            )

    def test_dial_config_update_validates_fallback_chain(self) -> None:
        with pytest.raises(ValidationError):
            DialConfigUpdate(fallback_chain={"captain": ["gemini"]})

    def test_dial_config_update_accepts_object_form(self) -> None:
        cfg = DialConfigUpdate(
            fallback_chain={"captain": [{"provider": "openai", "model": "gpt-4o"}]}
        )
        assert cfg.fallback_chain == {"captain": [{"provider": "openai", "model": "gpt-4o"}]}
