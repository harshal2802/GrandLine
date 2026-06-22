"""PlaywrightBrowserBackend — the opt-in REAL Bedside Browser backend.

Selected only by config (``GRANDLINE_BROWSER_BACKEND=playwright``); the default
stays ``NullBrowserBackend``. Playwright is **lazily imported inside ``run``** so
that importing this module — and therefore app startup and the whole test suite —
never requires Playwright to be installed. If Playwright is unavailable, ``run``
raises a clear ``BrowserBackendError`` (never an opaque ``ImportError``).

Playwright is an optional dependency: it is NOT in ``requirements.txt``. To use
this backend, install it explicitly::

    pip install playwright && python -m playwright install chromium
"""

from __future__ import annotations

import time

from app.browser.backend import BrowserBackendError, BrowserCheckBackend
from app.schemas.browser_check import BrowserCheckResult, BrowserCheckSpec


class PlaywrightBrowserBackend(BrowserCheckBackend):
    """Drives a real headless Chromium via Playwright (opt-in)."""

    def __init__(self, *, timeout_ms: int = 30000) -> None:
        self._timeout_ms = timeout_ms

    async def run(self, spec: BrowserCheckSpec) -> BrowserCheckResult:
        # Lazy import: keep Playwright out of module-load time so app startup and
        # the test suite never depend on it being installed.
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - exercised via patched import in tests
            raise BrowserBackendError(
                "Playwright is not installed. Install the optional Bedside Browser "
                "dependency with `pip install playwright && python -m playwright "
                "install chromium` to use the 'playwright' browser backend."
            ) from exc

        started = time.monotonic()
        console_errors: list[str] = []
        failed_assertions: list[str] = []
        screenshots: list[str] = []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                page.on(
                    "console",
                    lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
                )
                await page.goto(spec.url, timeout=self._timeout_ms)
                if spec.wait_for:
                    await page.wait_for_selector(spec.wait_for, timeout=self._timeout_ms)

                for assertion in spec.assertions:
                    if not await _evaluate_assertion(page, assertion):
                        failed_assertions.append(f"{assertion.type}: {assertion.value!r} not found")

                if spec.capture_screenshot:
                    data = await page.screenshot()
                    screenshots.append(f"playwright://{spec.name}/{len(data)}-bytes.png")
            finally:
                await browser.close()

        duration_ms = int((time.monotonic() - started) * 1000)
        return BrowserCheckResult(
            passed=not failed_assertions,
            screenshots=screenshots,
            console_errors=console_errors,
            failed_assertions=failed_assertions,
            duration_ms=duration_ms,
        )


async def _evaluate_assertion(page: object, assertion: object) -> bool:
    """Evaluate one assertion against a live Playwright page."""
    atype = assertion.type  # type: ignore[attr-defined]
    value = assertion.value  # type: ignore[attr-defined]
    if atype == "selector_present":
        locator = page.locator(value)  # type: ignore[attr-defined]
        return bool(await locator.count() > 0)
    if atype == "text_present":
        content = await page.content()  # type: ignore[attr-defined]
        return bool(value in content)
    return False
