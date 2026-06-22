"""Tests for the StandingOrder model (reusable voyage presets)."""

from sqlalchemy import inspect

from app.models import Base
from app.models.standing_order import StandingOrder


def test_standing_order_registered_in_metadata() -> None:
    assert "standing_orders" in Base.metadata.tables


def test_standing_order_columns() -> None:
    mapper = inspect(StandingOrder)
    column_names = {c.key for c in mapper.columns}
    assert column_names == {
        "id",
        "user_id",
        "name",
        "description",
        "target_repo",
        "dial_config",
        "plan_skeleton",
        "injected_context",
        "created_at",
        "updated_at",
    }


def test_user_id_is_indexed_not_nullable_fk() -> None:
    col = StandingOrder.__table__.c.user_id
    assert col.nullable is False
    assert col.index is True
    assert any(fk.column.table.name == "users" for fk in col.foreign_keys)


def test_name_is_required() -> None:
    col = StandingOrder.__table__.c.name
    assert col.nullable is False
    assert col.type.length == 255


def test_target_repo_nullable_500() -> None:
    col = StandingOrder.__table__.c.target_repo
    assert col.nullable is True
    assert col.type.length == 500


def test_dial_config_is_jsonb_nullable() -> None:
    col = StandingOrder.__table__.c.dial_config
    assert col.nullable is True
    assert col.type.__class__.__name__ == "JSONB"


def test_plan_skeleton_is_jsonb_nullable() -> None:
    col = StandingOrder.__table__.c.plan_skeleton
    assert col.nullable is True
    assert col.type.__class__.__name__ == "JSONB"


def test_injected_context_is_text_nullable() -> None:
    col = StandingOrder.__table__.c.injected_context
    assert col.nullable is True
    assert col.type.__class__.__name__ == "Text"


def test_unique_user_name_constraint_present() -> None:
    constraint_names = {c.name for c in StandingOrder.__table__.constraints}
    assert "uq_standing_orders_user_name" in constraint_names
