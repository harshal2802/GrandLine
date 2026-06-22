"""Tests for the Log Book REST API endpoints (direct endpoint calls)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.log_book import LogBookEntry
from app.schemas.log_book import LogBookEntryCreate

REPO = "github.com/acme/widgets"


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


def _row(kind: str = "layout", content: str = "src/ holds backend") -> LogBookEntry:
    entry = LogBookEntry(repo=REPO, author="captain", kind=kind, content=content)
    entry.id = uuid.uuid4()
    entry.voyage_id = None
    entry.details = {}
    entry.created_at = datetime(2026, 6, 22, tzinfo=UTC)
    return entry


class TestRecallEndpoint:
    @pytest.mark.asyncio
    async def test_returns_entries(self) -> None:
        from app.api.v1.log_book import recall_log_book

        svc = AsyncMock()
        svc.recall = AsyncMock(return_value=[_row("layout"), _row("decision")])

        result = await recall_log_book(REPO, 20, _mock_user(), svc)

        assert len(result) == 2
        assert result[0].repo == REPO
        svc.recall.assert_awaited_once_with(REPO, limit=20)

    @pytest.mark.asyncio
    async def test_returns_empty_list(self) -> None:
        from app.api.v1.log_book import recall_log_book

        svc = AsyncMock()
        svc.recall = AsyncMock(return_value=[])

        result = await recall_log_book(REPO, 20, _mock_user(), svc)

        assert result == []


class TestRecordEndpoint:
    @pytest.mark.asyncio
    async def test_records_entry(self) -> None:
        from app.api.v1.log_book import record_log_book_entry

        row = _row("gotcha", "DB up first")
        svc = AsyncMock()
        svc.record = AsyncMock(return_value=row)
        body = LogBookEntryCreate(
            repo=REPO,
            author="captain",
            kind="gotcha",
            content="DB up first",
        )

        result = await record_log_book_entry(body, _mock_user(), svc)

        assert result.kind == "gotcha"
        assert result.content == "DB up first"
        svc.record.assert_awaited_once_with(
            REPO,
            "captain",
            "gotcha",
            "DB up first",
            details={},
            voyage_id=None,
        )
