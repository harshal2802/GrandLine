"""Tests for the Bedside Browser backends (Phase 23).

Mirrors test_deployment_backend / test_execution_backend: Null backend
determinism, factory selection + unknown -> ValueError, and the Playwright
backend raising cleanly when its lazily-imported library is absent (patched
import — no real browser, no Playwright install required).
"""

from __future__ import annotations

import builtins
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.browser.backend import BrowserBackendError
from app.browser.factory import create_browser_backend
from app.browser.null_backend import NullBrowserBackend
from app.browser.playwright_backend import PlaywrightBrowserBackend
from app.schemas.browser_check import BrowserAssertion, BrowserCheckSpec


class TestNullBackendDeterminism:
    async def test_passes_with_non_empty_assertions(self) -> None:
        backend = NullBrowserBackend()
        spec = BrowserCheckSpec(
            name="home",
            url="http://localhost:3000",
            assertions=[
                BrowserAssertion(type="selector_present", value="#app"),
                BrowserAssertion(type="text_present", value="Welcome"),
            ],
        )
        result = await backend.run(spec)
        assert result.passed is True
        assert result.failed_assertions == []

    async def test_fails_on_empty_assertion_value(self) -> None:
        backend = NullBrowserBackend()
        spec = BrowserCheckSpec(
            name="home",
            url="http://localhost:3000",
            assertions=[BrowserAssertion(type="text_present", value="")],
        )
        result = await backend.run(spec)
        assert result.passed is False
        assert len(result.failed_assertions) == 1

    async def test_screenshot_ref_placeholder(self) -> None:
        backend = NullBrowserBackend()
        spec = BrowserCheckSpec(name="dash", url="http://localhost:3000")
        result = await backend.run(spec)
        assert result.screenshots == ["null-backend://dash.png"]

    async def test_no_screenshot_when_disabled(self) -> None:
        backend = NullBrowserBackend()
        spec = BrowserCheckSpec(name="dash", url="http://localhost:3000", capture_screenshot=False)
        result = await backend.run(spec)
        assert result.screenshots == []

    async def test_deterministic_repeatable(self) -> None:
        backend = NullBrowserBackend()
        spec = BrowserCheckSpec(name="home", url="http://localhost:3000")
        r1 = await backend.run(spec)
        r2 = await backend.run(spec)
        assert r1.model_dump() == r2.model_dump()

    async def test_close_is_noop(self) -> None:
        backend = NullBrowserBackend()
        await backend.close()  # must not raise


class TestFactorySelection:
    def test_default_is_null(self) -> None:
        backend = create_browser_backend(SimpleNamespace())
        assert isinstance(backend, NullBrowserBackend)

    def test_explicit_null(self) -> None:
        backend = create_browser_backend(SimpleNamespace(browser_backend="null"))
        assert isinstance(backend, NullBrowserBackend)

    def test_playwright_selected(self) -> None:
        backend = create_browser_backend(SimpleNamespace(browser_backend="playwright"))
        assert isinstance(backend, PlaywrightBrowserBackend)

    def test_unknown_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown browser backend"):
            create_browser_backend(SimpleNamespace(browser_backend="selenium"))


class TestPlaywrightBackendMissingLib:
    async def test_raises_clean_error_when_playwright_absent(self) -> None:
        backend = PlaywrightBrowserBackend()
        spec = BrowserCheckSpec(name="home", url="http://localhost:3000")

        real_import = builtins.__import__

        def _fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("playwright"):
                raise ImportError("No module named 'playwright'")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _fake_import):
            with pytest.raises(BrowserBackendError, match="Playwright is not installed"):
                await backend.run(spec)
