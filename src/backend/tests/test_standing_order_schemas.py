"""Tests for Standing Order Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.standing_order import (
    ChartFromStandingOrderRequest,
    StandingOrderCreate,
    StandingOrderRead,
    StandingOrderUpdate,
)


class TestStandingOrderCreate:
    def test_minimal_valid(self) -> None:
        order = StandingOrderCreate(name="bugfix voyage")
        assert order.name == "bugfix voyage"
        assert order.dial_config is None
        assert order.target_repo is None

    def test_full_valid(self) -> None:
        order = StandingOrderCreate(
            name="dep-bump voyage",
            description="Routine dependency bumps",
            target_repo="github.com/acme/widgets",
            dial_config={
                "role_mapping": {"captain": {"provider": "anthropic", "model": "x"}},
                "fallback_chain": {"captain": ["openai"]},
            },
            plan_skeleton={"phases": []},
            injected_context="Follow the repo's conventions.md",
        )
        assert order.dial_config is not None
        assert order.injected_context == "Follow the repo's conventions.md"

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValidationError):
            StandingOrderCreate(name="")

    def test_rejects_non_dict_role_mapping(self) -> None:
        with pytest.raises(ValidationError):
            StandingOrderCreate(name="x", dial_config={"role_mapping": ["not", "a", "dict"]})

    def test_rejects_unsupported_fallback_provider(self) -> None:
        with pytest.raises(ValidationError):
            StandingOrderCreate(
                name="x",
                dial_config={"fallback_chain": {"captain": ["nope-provider"]}},
            )

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            StandingOrderCreate(name="x", bogus="y")


class TestStandingOrderUpdate:
    def test_all_optional(self) -> None:
        upd = StandingOrderUpdate()
        assert upd.model_dump(exclude_unset=True) == {}

    def test_partial(self) -> None:
        upd = StandingOrderUpdate(description="new desc")
        assert upd.model_dump(exclude_unset=True) == {"description": "new desc"}


class TestStandingOrderRead:
    def test_from_attributes(self) -> None:
        class _Row:
            id = uuid.uuid4()
            user_id = uuid.uuid4()
            name = "bugfix voyage"
            description = None
            target_repo = "github.com/acme/widgets"
            dial_config = None
            plan_skeleton = None
            injected_context = None
            created_at = datetime(2026, 6, 22, tzinfo=UTC)
            updated_at = datetime(2026, 6, 22, tzinfo=UTC)

        read = StandingOrderRead.model_validate(_Row())
        assert read.name == "bugfix voyage"
        assert read.target_repo == "github.com/acme/widgets"


class TestChartFromStandingOrderRequest:
    def test_valid(self) -> None:
        req = ChartFromStandingOrderRequest(task="Fix the flaky login test in auth module")
        assert req.title is None
        assert req.target_repo is None

    def test_overrides(self) -> None:
        req = ChartFromStandingOrderRequest(
            task="Fix the flaky login test in auth module",
            title="Custom title",
            target_repo="github.com/acme/other",
        )
        assert req.title == "Custom title"

    def test_rejects_short_task(self) -> None:
        with pytest.raises(ValidationError):
            ChartFromStandingOrderRequest(task="too short")
