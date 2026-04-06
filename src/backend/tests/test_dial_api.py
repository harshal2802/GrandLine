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
