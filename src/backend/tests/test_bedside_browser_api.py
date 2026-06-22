"""Tests for the Bedside Browser REST API (direct endpoint calls)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.browser.null_backend import NullBrowserBackend
from app.schemas.browser_check import BrowserAssertion, BrowserCheckSpec

VOYAGE_ID = uuid.uuid4()


def _voyage() -> MagicMock:
    v = MagicMock()
    v.id = VOYAGE_ID
    return v


def _row(passed: bool = True) -> MagicMock:
    row = MagicMock()
    row.id = uuid.uuid4()
    row.voyage_id = VOYAGE_ID
    row.phase_number = 2
    row.url = "http://localhost:3000"
    row.passed = passed
    row.screenshot_ref = "null-backend://home.png"
    row.console_errors = []
    row.failed_assertions = []
    row.created_at = datetime.now(UTC)
    return row


class TestRunBrowserCheck:
    @pytest.mark.asyncio
    async def test_returns_201_browser_check_read(self) -> None:
        from app.api.v1.bedside_browser import run_browser_check

        service = AsyncMock()
        service.run_browser_check = AsyncMock(return_value=_row())
        spec = BrowserCheckSpec(
            name="home",
            url="http://localhost:3000",
            assertions=[BrowserAssertion(type="selector_present", value="#app")],
        )

        result = await run_browser_check(
            VOYAGE_ID,
            2,
            spec,
            user=MagicMock(),
            voyage=_voyage(),
            service=service,
            backend=NullBrowserBackend(),
        )

        assert result.passed is True
        assert result.screenshot_ref == "null-backend://home.png"
        service.run_browser_check.assert_awaited_once()
        # The backend is passed through to the service.
        _, kwargs = service.run_browser_check.call_args
        passed_args = service.run_browser_check.call_args.args
        assert any(isinstance(a, NullBrowserBackend) for a in passed_args) or isinstance(
            kwargs.get("backend"), NullBrowserBackend
        )


class TestListBrowserChecks:
    @pytest.mark.asyncio
    async def test_returns_list(self) -> None:
        from app.api.v1.bedside_browser import list_browser_checks

        service = AsyncMock()
        service.list_browser_checks = AsyncMock(return_value=[_row(), _row(passed=False)])

        result = await list_browser_checks(
            VOYAGE_ID, user=MagicMock(), voyage=_voyage(), service=service
        )

        assert len(result) == 2
        assert result[0].passed is True
        assert result[1].passed is False


class TestOwnerScoping:
    @pytest.mark.asyncio
    async def test_missing_or_unowned_voyage_is_404_via_dependency(self) -> None:
        from app.api.v1.dependencies import get_authorized_voyage

        session = AsyncMock()
        empty = MagicMock()
        empty.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=empty)
        user = MagicMock()
        user.id = uuid.uuid4()

        with pytest.raises(HTTPException) as exc:
            await get_authorized_voyage(VOYAGE_ID, session, user)

        assert exc.value.status_code == 404
