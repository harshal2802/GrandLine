"""Tests for LogBookService (mocked AsyncSession — no database)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.log_book import LogBookEntry
from app.services.log_book_service import LogBookService

REPO = "github.com/acme/widgets"


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _entry(kind: str, content: str) -> LogBookEntry:
    return LogBookEntry(repo=REPO, author="captain", kind=kind, content=content)


def _execute_returning(entries: list[LogBookEntry]) -> MagicMock:
    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = entries
    result_mock.scalars.return_value = scalars_mock
    return result_mock


class TestRecord:
    @pytest.mark.asyncio
    async def test_record_adds_flushes_commits_refreshes(self) -> None:
        session = _mock_session()
        service = LogBookService(session)

        entry = await service.record(REPO, "captain", "layout", "src/ holds backend")

        session.add.assert_called_once()
        added = session.add.call_args.args[0]
        assert isinstance(added, LogBookEntry)
        assert added.repo == REPO
        assert added.kind == "layout"
        assert added.details == {}
        session.flush.assert_awaited_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(entry)

    @pytest.mark.asyncio
    async def test_record_carries_details_and_voyage_id(self) -> None:
        session = _mock_session()
        service = LogBookService(session)
        vid = uuid.uuid4()

        entry = await service.record(
            REPO,
            "user",
            "gotcha",
            "DB must be up",
            details={"path": "alembic/"},
            voyage_id=vid,
        )

        assert entry.details == {"path": "alembic/"}
        assert entry.voyage_id == vid


class TestRecall:
    @pytest.mark.asyncio
    async def test_recall_returns_entries(self) -> None:
        session = _mock_session()
        entries = [_entry("layout", "a"), _entry("decision", "b")]
        session.execute = AsyncMock(return_value=_execute_returning(entries))
        service = LogBookService(session)

        result = await service.recall(REPO)

        assert result == entries
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_recall_empty(self) -> None:
        session = _mock_session()
        session.execute = AsyncMock(return_value=_execute_returning([]))
        service = LogBookService(session)

        result = await service.recall(REPO)

        assert result == []


class TestRenderContext:
    @pytest.mark.asyncio
    async def test_render_context_formats_block(self) -> None:
        session = _mock_session()
        entries = [_entry("layout", "src/ holds backend"), _entry("gotcha", "DB up first")]
        session.execute = AsyncMock(return_value=_execute_returning(entries))
        service = LogBookService(session)

        rendered = await service.render_context(REPO)

        assert rendered.startswith(f"## Log Book — prior knowledge for {REPO}")
        assert "- (layout) src/ holds backend" in rendered
        assert "- (gotcha) DB up first" in rendered

    @pytest.mark.asyncio
    async def test_render_context_empty_returns_empty_string(self) -> None:
        session = _mock_session()
        session.execute = AsyncMock(return_value=_execute_returning([]))
        service = LogBookService(session)

        rendered = await service.render_context(REPO)

        assert rendered == ""


class TestReader:
    def test_reader_returns_instance(self) -> None:
        session = _mock_session()
        reader = LogBookService.reader(session)
        assert isinstance(reader, LogBookService)
