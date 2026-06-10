"""Tests for Dial System REST API endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dial_config import DialConfig
from app.schemas.dial_config import DialConfigUpdate

VOYAGE_ID = uuid.uuid4()
CONFIG_ID = uuid.uuid4()

ROLE_MAPPING = {
    "captain": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    "navigator": {"provider": "openai", "model": "gpt-4o"},
}

FALLBACK_CHAIN = {
    "captain": ["openai", "ollama"],
}


def _mock_session_with_config(config: DialConfig | None) -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = config
    session.execute.return_value = mock_result
    return session


class TestGetDialConfig:
    @pytest.mark.asyncio
    async def test_get_dial_config_returns_config(self) -> None:
        from app.api.v1.dial import get_dial_config

        config = DialConfig(
            id=CONFIG_ID,
            voyage_id=VOYAGE_ID,
            role_mapping=ROLE_MAPPING,
            fallback_chain=FALLBACK_CHAIN,
        )
        session = _mock_session_with_config(config)
        user = MagicMock()

        result = await get_dial_config(VOYAGE_ID, session, user)

        assert result.voyage_id == VOYAGE_ID
        assert result.role_mapping == ROLE_MAPPING

    @pytest.mark.asyncio
    async def test_get_dial_config_not_found_raises_404(self) -> None:
        from app.api.v1.dial import get_dial_config

        session = _mock_session_with_config(None)
        user = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_dial_config(VOYAGE_ID, session, user)

        assert exc_info.value.status_code == 404


class TestUpdateDialConfig:
    @pytest.mark.asyncio
    async def test_update_dial_config_updates_fields(self) -> None:
        from app.api.v1.dial import update_dial_config

        config = DialConfig(
            id=CONFIG_ID,
            voyage_id=VOYAGE_ID,
            role_mapping=ROLE_MAPPING,
            fallback_chain=FALLBACK_CHAIN,
        )
        session = _mock_session_with_config(config)
        user = MagicMock()

        new_mapping = {
            "captain": {"provider": "openai", "model": "gpt-4o"},
        }
        update = DialConfigUpdate(role_mapping=new_mapping)

        result = await update_dial_config(VOYAGE_ID, update, session, user)

        assert result.role_mapping == new_mapping
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_dial_config_not_found_raises_404(self) -> None:
        from app.api.v1.dial import update_dial_config

        session = _mock_session_with_config(None)
        user = MagicMock()
        update = DialConfigUpdate(role_mapping=ROLE_MAPPING)

        with pytest.raises(HTTPException) as exc_info:
            await update_dial_config(VOYAGE_ID, update, session, user)

        assert exc_info.value.status_code == 404


class TestProvidersInConfig:
    def test_collects_mapping_and_fallback_providers(self) -> None:
        from app.api.v1.dial import _providers_in_config

        providers = _providers_in_config(
            {"captain": {"provider": "anthropic", "model": "x"}},
            {"captain": ["openai", {"provider": "ollama", "model": "llama3"}]},
        )
        assert providers == ["anthropic", "ollama", "openai"]  # sorted, deduped

    def test_handles_none(self) -> None:
        from app.api.v1.dial import _providers_in_config

        assert _providers_in_config(None, None) == []


class TestGetDialStatus:
    @staticmethod
    def _redis(requests: int = 0, entries: list[tuple[str, float]] | None = None) -> AsyncMock:
        redis = AsyncMock()
        redis.zrangebyscore = AsyncMock(return_value=entries or [])
        redis.zcount = AsyncMock(return_value=requests)
        return redis

    @pytest.mark.asyncio
    async def test_returns_usage_for_each_provider(self) -> None:
        from app.api.v1.dial import get_dial_status

        config = DialConfig(
            id=CONFIG_ID,
            voyage_id=VOYAGE_ID,
            role_mapping=ROLE_MAPPING,
            fallback_chain=FALLBACK_CHAIN,
        )
        session = _mock_session_with_config(config)

        result = await get_dial_status(VOYAGE_ID, session, self._redis(), MagicMock())

        assert result.window_seconds == 60
        names = {p.provider for p in result.providers}
        assert names == {"anthropic", "openai", "ollama"}
        for p in result.providers:
            assert p.is_limited is False
            assert p.remaining_requests == 100
            assert p.remaining_tokens == 100_000
            assert p.max_requests == 100
            assert p.max_tokens == 100_000

    @pytest.mark.asyncio
    async def test_reflects_consumed_window(self) -> None:
        from app.api.v1.dial import get_dial_status

        config = DialConfig(
            id=CONFIG_ID,
            voyage_id=VOYAGE_ID,
            role_mapping={"captain": {"provider": "anthropic", "model": "x"}},
            fallback_chain=None,
        )
        session = _mock_session_with_config(config)
        # 3 requests, 1500 tokens consumed this window.
        redis = self._redis(requests=3, entries=[("1.0:1000", 1.0), ("2.0:500", 2.0)])

        result = await get_dial_status(VOYAGE_ID, session, redis, MagicMock())

        anthropic = next(p for p in result.providers if p.provider == "anthropic")
        assert anthropic.remaining_requests == 97
        assert anthropic.remaining_tokens == 98_500

    @pytest.mark.asyncio
    async def test_404_when_no_config(self) -> None:
        from app.api.v1.dial import get_dial_status

        session = _mock_session_with_config(None)

        with pytest.raises(HTTPException) as exc_info:
            await get_dial_status(VOYAGE_ID, session, self._redis(), MagicMock())

        assert exc_info.value.status_code == 404
