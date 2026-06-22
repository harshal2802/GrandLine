"""Tests for Log Book Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.log_book import (
    LogBookEntryCreate,
    LogBookEntryRead,
    RecalledContext,
)


class TestLogBookEntryCreate:
    def test_valid_entry(self) -> None:
        entry = LogBookEntryCreate(
            repo="github.com/acme/widgets",
            author="captain",
            kind="layout",
            content="src/ holds the backend, web/ the frontend",
        )
        assert entry.kind == "layout"
        assert entry.details == {}
        assert entry.voyage_id is None

    def test_accepts_optional_fields(self) -> None:
        vid = uuid.uuid4()
        entry = LogBookEntryCreate(
            repo="r",
            author="user",
            kind="gotcha",
            content="migrations need DB up first",
            details={"path": "alembic/"},
            voyage_id=vid,
        )
        assert entry.voyage_id == vid
        assert entry.details == {"path": "alembic/"}

    def test_rejects_unknown_kind(self) -> None:
        with pytest.raises(ValidationError):
            LogBookEntryCreate(
                repo="r",
                author="captain",
                kind="random",
                content="x",
            )

    def test_rejects_empty_content(self) -> None:
        with pytest.raises(ValidationError):
            LogBookEntryCreate(repo="r", author="captain", kind="summary", content="")

    def test_rejects_empty_repo(self) -> None:
        with pytest.raises(ValidationError):
            LogBookEntryCreate(repo="", author="captain", kind="summary", content="x")

    def test_all_allowed_kinds(self) -> None:
        for kind in ("convention", "decision", "layout", "gotcha", "summary"):
            entry = LogBookEntryCreate(repo="r", author="captain", kind=kind, content="x")
            assert entry.kind == kind


class TestLogBookEntryRead:
    def test_from_attributes(self) -> None:
        class _Row:
            id = uuid.uuid4()
            repo = "github.com/acme/widgets"
            voyage_id = None
            author = "captain"
            kind = "convention"
            content = "themed naming everywhere"
            details: dict[str, object] = {}
            created_at = datetime(2026, 6, 22, tzinfo=UTC)

        read = LogBookEntryRead.model_validate(_Row())
        assert read.repo == "github.com/acme/widgets"
        assert read.kind == "convention"


class TestRecalledContext:
    def test_defaults(self) -> None:
        ctx = RecalledContext(repo="r")
        assert ctx.entries == []
        assert ctx.rendered == ""
