"""Tests for POST /voyages (chart a course)."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.api.v1.voyages import create_voyage
from app.models.dial_config import DialConfig
from app.models.enums import CrewRole, VoyageStatus
from app.models.voyage import Voyage
from app.schemas.voyage import VoyageCreate

USER_ID = uuid.uuid4()


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = USER_ID
    user.is_active = True
    return user


def _mock_session(added: list[Any]) -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock(side_effect=added.append)
    return session


class TestCreateVoyage:
    @pytest.mark.asyncio
    async def test_creates_charted_voyage_for_current_user(self) -> None:
        added: list[Any] = []
        session = _mock_session(added)

        voyage = await create_voyage(
            VoyageCreate(title="Find One Piece", description="Sail the GrandLine"),
            session=session,
            user=_mock_user(),
        )

        assert isinstance(voyage, Voyage)
        assert voyage.user_id == USER_ID
        assert voyage.title == "Find One Piece"
        assert voyage.description == "Sail the GrandLine"
        assert voyage.status == VoyageStatus.CHARTED.value
        assert voyage.phase_status == {}
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(voyage)

    @pytest.mark.asyncio
    async def test_creates_default_dial_config_for_all_roles(self) -> None:
        added: list[Any] = []
        session = _mock_session(added)

        voyage = await create_voyage(
            VoyageCreate(title="Find One Piece"),
            session=session,
            user=_mock_user(),
        )

        dial_configs = [obj for obj in added if isinstance(obj, DialConfig)]
        assert len(dial_configs) == 1
        config = dial_configs[0]
        assert config.voyage_id == voyage.id
        assert set(config.role_mapping) == {role.value for role in CrewRole}
        for role_cfg in config.role_mapping.values():
            assert role_cfg["provider"]
            assert role_cfg["model"]
        assert config.fallback_chain is None

    @pytest.mark.asyncio
    async def test_optional_fields_default_to_none(self) -> None:
        added: list[Any] = []
        session = _mock_session(added)

        voyage = await create_voyage(
            VoyageCreate(title="Find One Piece"),
            session=session,
            user=_mock_user(),
        )

        assert voyage.description is None
        assert voyage.target_repo is None

    def test_rejects_empty_title(self) -> None:
        with pytest.raises(ValidationError):
            VoyageCreate(title="")

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            VoyageCreate(title="x", status="COMPLETED")  # type: ignore[call-arg]
