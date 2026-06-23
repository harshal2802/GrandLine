"""Tests for the per-role claude_code sub-schema and resolver (Phase C1)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.dial_config import (
    ClaudeCodeRoleConfig,
    resolve_claude_code_role_config,
)


class TestClaudeCodeRoleConfig:
    def test_accepts_none(self) -> None:
        cfg = ClaudeCodeRoleConfig(max_turns=None)
        assert cfg.max_turns is None

    def test_accepts_default(self) -> None:
        cfg = ClaudeCodeRoleConfig()
        assert cfg.max_turns is None

    def test_accepts_one(self) -> None:
        cfg = ClaudeCodeRoleConfig(max_turns=1)
        assert cfg.max_turns == 1

    def test_accepts_ten(self) -> None:
        cfg = ClaudeCodeRoleConfig(max_turns=10)
        assert cfg.max_turns == 10

    def test_rejects_zero(self) -> None:
        with pytest.raises(ValidationError):
            ClaudeCodeRoleConfig(max_turns=0)

    def test_rejects_eleven(self) -> None:
        with pytest.raises(ValidationError):
            ClaudeCodeRoleConfig(max_turns=11)

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValidationError):
            ClaudeCodeRoleConfig(max_turns=-1)

    def test_rejects_string(self) -> None:
        with pytest.raises(ValidationError):
            ClaudeCodeRoleConfig(max_turns="3")  # type: ignore[arg-type]


class TestResolveClaudeCodeRoleConfig:
    def test_returns_defaults_when_none(self) -> None:
        assert resolve_claude_code_role_config(None).max_turns is None

    def test_returns_defaults_when_not_a_dict(self) -> None:
        assert resolve_claude_code_role_config("sonnet").max_turns is None  # type: ignore[arg-type]

    def test_returns_defaults_when_list(self) -> None:
        assert resolve_claude_code_role_config([1, 2, 3]).max_turns is None  # type: ignore[arg-type]

    def test_returns_value_when_valid(self) -> None:
        role_cfg: dict[str, Any] = {"max_turns": 4}
        assert resolve_claude_code_role_config(role_cfg).max_turns == 4

    def test_returns_defaults_when_max_turns_is_zero(self) -> None:
        assert resolve_claude_code_role_config({"max_turns": 0}).max_turns is None

    def test_returns_defaults_when_max_turns_too_large(self) -> None:
        assert resolve_claude_code_role_config({"max_turns": 99}).max_turns is None

    def test_returns_defaults_when_max_turns_negative(self) -> None:
        assert resolve_claude_code_role_config({"max_turns": -5}).max_turns is None

    def test_returns_defaults_when_max_turns_is_string(self) -> None:
        assert resolve_claude_code_role_config({"max_turns": "3"}).max_turns is None

    def test_returns_defaults_when_max_turns_absent(self) -> None:
        assert resolve_claude_code_role_config({}).max_turns is None

    def test_returns_defaults_when_max_turns_is_none_value(self) -> None:
        assert resolve_claude_code_role_config({"max_turns": None}).max_turns is None

    def test_tolerates_sibling_provider_and_model_keys(self) -> None:
        role_cfg: dict[str, Any] = {
            "provider": "claude_code",
            "model": "sonnet",
            "max_turns": 5,
        }
        assert resolve_claude_code_role_config(role_cfg).max_turns == 5

    def test_tolerates_sibling_keys_without_max_turns(self) -> None:
        role_cfg: dict[str, Any] = {"provider": "claude_code", "model": "sonnet"}
        assert resolve_claude_code_role_config(role_cfg).max_turns is None
