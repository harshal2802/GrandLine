"""Tests for Bedside Browser schemas (Phase 23)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.browser_check import (
    BrowserAssertion,
    BrowserCheckRead,
    BrowserCheckResult,
    BrowserCheckSpec,
)


class TestBrowserAssertion:
    def test_selector_present(self) -> None:
        a = BrowserAssertion(type="selector_present", value="#app")
        assert a.type == "selector_present"
        assert a.value == "#app"

    def test_text_present(self) -> None:
        a = BrowserAssertion(type="text_present", value="Welcome")
        assert a.type == "text_present"

    def test_rejects_unknown_type(self) -> None:
        with pytest.raises(ValidationError):
            BrowserAssertion(type="color_present", value="x")  # type: ignore[arg-type]


class TestBrowserCheckSpec:
    def test_minimal(self) -> None:
        spec = BrowserCheckSpec(name="home", url="http://localhost:3000")
        assert spec.capture_screenshot is True
        assert spec.assertions == []
        assert spec.wait_for is None

    def test_full(self) -> None:
        spec = BrowserCheckSpec(
            name="home",
            url="http://localhost:3000",
            wait_for="#app",
            assertions=[BrowserAssertion(type="text_present", value="Welcome")],
            capture_screenshot=False,
        )
        assert spec.wait_for == "#app"
        assert len(spec.assertions) == 1
        assert spec.capture_screenshot is False

    def test_requires_name_and_url(self) -> None:
        with pytest.raises(ValidationError):
            BrowserCheckSpec(name="", url="http://x")
        with pytest.raises(ValidationError):
            BrowserCheckSpec(name="home", url="")


class TestBrowserCheckResult:
    def test_defaults(self) -> None:
        r = BrowserCheckResult(passed=True, duration_ms=12)
        assert r.screenshots == []
        assert r.console_errors == []
        assert r.failed_assertions == []

    def test_rejects_negative_duration(self) -> None:
        with pytest.raises(ValidationError):
            BrowserCheckResult(passed=True, duration_ms=-1)


class TestBrowserCheckRead:
    def test_from_attributes(self) -> None:
        class _Row:
            id = uuid.uuid4()
            voyage_id = uuid.uuid4()
            phase_number = 3
            url = "http://localhost:3000"
            passed = True
            screenshot_ref = "null-backend://home.png"
            console_errors: list[str] = []
            failed_assertions: list[str] = []
            created_at = datetime.now(UTC)

        read = BrowserCheckRead.model_validate(_Row())
        assert read.passed is True
        assert read.screenshot_ref == "null-backend://home.png"
        assert read.phase_number == 3
