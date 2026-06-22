"""Tests for the LogBookEntry model (Log Book — cross-voyage memory)."""

from sqlalchemy import inspect

from app.models import Base
from app.models.log_book import LogBookEntry


def test_log_book_entry_registered_in_metadata() -> None:
    assert "log_book_entries" in Base.metadata.tables


def test_log_book_entry_columns() -> None:
    mapper = inspect(LogBookEntry)
    column_names = {c.key for c in mapper.columns}
    assert column_names == {
        "id",
        "repo",
        "voyage_id",
        "author",
        "kind",
        "content",
        "details",
        "created_at",
    }


def test_repo_is_indexed_not_nullable() -> None:
    col = LogBookEntry.__table__.c.repo
    assert col.nullable is False
    assert col.index is True
    assert col.type.length == 500


def test_voyage_id_is_nullable_fk() -> None:
    col = LogBookEntry.__table__.c.voyage_id
    assert col.nullable is True
    assert any(fk.column.table.name == "voyages" for fk in col.foreign_keys)


def test_content_is_text_and_required() -> None:
    col = LogBookEntry.__table__.c.content
    assert col.nullable is False
    assert col.type.__class__.__name__ == "Text"


def test_details_is_jsonb_not_nullable() -> None:
    col = LogBookEntry.__table__.c.details
    assert col.nullable is False
    assert col.type.__class__.__name__ == "JSONB"


def test_repo_created_composite_index_present() -> None:
    index_names = {idx.name for idx in LogBookEntry.__table__.indexes}
    assert "ix_log_book_entries_repo_created" in index_names
