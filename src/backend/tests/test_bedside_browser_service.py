"""Tests for BedsideBrowserService (mocked session + Null backend)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.browser.null_backend import NullBrowserBackend
from app.models.browser_check import BrowserCheck
from app.models.crew_action import CrewAction
from app.schemas.browser_check import BrowserAssertion, BrowserCheckSpec
from app.services.bedside_browser_service import BedsideBrowserService
from app.services.crew_action_helper import CrewActionType

VOYAGE_ID = uuid.uuid4()


def _mock_voyage() -> MagicMock:
    v = MagicMock()
    v.id = VOYAGE_ID
    return v


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_mushi() -> AsyncMock:
    mushi = AsyncMock()
    mushi.publish = AsyncMock(return_value="msg-1")
    return mushi


class TestRunBrowserCheck:
    async def test_persists_browser_check_row(
        self, mock_session: AsyncMock, mock_mushi: AsyncMock
    ) -> None:
        service = BedsideBrowserService(mock_session, mock_mushi)
        spec = BrowserCheckSpec(
            name="home",
            url="http://localhost:3000",
            assertions=[BrowserAssertion(type="selector_present", value="#app")],
        )

        check = await service.run_browser_check(
            _mock_voyage(), phase_number=2, spec=spec, backend=NullBrowserBackend()
        )

        added = [c.args[0] for c in mock_session.add.call_args_list]
        browser_checks = [a for a in added if isinstance(a, BrowserCheck)]
        assert len(browser_checks) == 1
        row = browser_checks[0]
        assert row.voyage_id == VOYAGE_ID
        assert row.phase_number == 2
        assert row.url == "http://localhost:3000"
        assert row.passed is True
        assert row.screenshot_ref == "null-backend://home.png"
        assert check is row
        mock_session.commit.assert_awaited_once()

    async def test_records_browser_check_run_crew_action_with_screenshot(
        self, mock_session: AsyncMock, mock_mushi: AsyncMock
    ) -> None:
        service = BedsideBrowserService(mock_session, mock_mushi)
        spec = BrowserCheckSpec(name="home", url="http://localhost:3000")

        await service.run_browser_check(
            _mock_voyage(), phase_number=1, spec=spec, backend=NullBrowserBackend()
        )

        added = [c.args[0] for c in mock_session.add.call_args_list]
        actions = [a for a in added if isinstance(a, CrewAction)]
        assert len(actions) == 1
        action = actions[0]
        assert action.action_type == CrewActionType.BROWSER_CHECK_RUN.value
        assert action.crew_member == "doctor"
        assert action.details["screenshot_ref"] == "null-backend://home.png"
        assert action.details["passed"] is True

    async def test_failed_check_records_failed_assertions(
        self, mock_session: AsyncMock, mock_mushi: AsyncMock
    ) -> None:
        service = BedsideBrowserService(mock_session, mock_mushi)
        spec = BrowserCheckSpec(
            name="broken",
            url="http://localhost:3000",
            assertions=[BrowserAssertion(type="text_present", value="")],
        )

        check = await service.run_browser_check(
            _mock_voyage(), phase_number=None, spec=spec, backend=NullBrowserBackend()
        )

        assert check.passed is False
        assert len(check.failed_assertions) == 1

    async def test_publishes_crew_action_event_best_effort(
        self, mock_session: AsyncMock, mock_mushi: AsyncMock
    ) -> None:
        service = BedsideBrowserService(mock_session, mock_mushi)
        spec = BrowserCheckSpec(name="home", url="http://localhost:3000")

        await service.run_browser_check(
            _mock_voyage(), phase_number=1, spec=spec, backend=NullBrowserBackend()
        )

        mock_mushi.publish.assert_awaited()

    async def test_publish_failure_does_not_raise(self, mock_session: AsyncMock) -> None:
        mushi = AsyncMock()
        mushi.publish = AsyncMock(side_effect=RuntimeError("redis down"))
        service = BedsideBrowserService(mock_session, mushi)
        spec = BrowserCheckSpec(name="home", url="http://localhost:3000")

        # Must not raise despite the publish failure.
        check = await service.run_browser_check(
            _mock_voyage(), phase_number=1, spec=spec, backend=NullBrowserBackend()
        )
        assert isinstance(check, BrowserCheck)


class TestListBrowserChecks:
    async def test_list_returns_rows(self, mock_session: AsyncMock) -> None:
        rows = [MagicMock(spec=BrowserCheck), MagicMock(spec=BrowserCheck)]
        result_obj = MagicMock()
        result_obj.scalars.return_value.all.return_value = rows
        mock_session.execute = AsyncMock(return_value=result_obj)

        service = BedsideBrowserService(mock_session)
        out = await service.list_browser_checks(VOYAGE_ID)

        assert out == rows
        mock_session.execute.assert_awaited_once()
