"""NullBrowserBackend — the deterministic v1 default for the Bedside Browser.

The analogue of ``InProcessDeploymentBackend``: no real browser, fully
deterministic, CI-safe. It evaluates each assertion against the spec without
ever loading a page — an assertion passes unless its ``value`` is empty (an
empty selector/text is treated as a malformed, failing assertion). When
``capture_screenshot`` is set it returns a placeholder screenshot ref so the
Ship's Log surfacing path is exercised end-to-end without a browser.
"""

from __future__ import annotations

from app.browser.backend import BrowserCheckBackend
from app.schemas.browser_check import (
    BrowserAssertion,
    BrowserCheckResult,
    BrowserCheckSpec,
)


class NullBrowserBackend(BrowserCheckBackend):
    """Deterministic, browser-free backend used for v1 and tests."""

    async def run(self, spec: BrowserCheckSpec) -> BrowserCheckResult:
        failed_assertions: list[str] = []
        for assertion in spec.assertions:
            if not _assertion_passes(assertion):
                failed_assertions.append(
                    f"{assertion.type}: expected non-empty value, got {assertion.value!r}"
                )

        passed = not failed_assertions
        screenshots: list[str] = []
        if spec.capture_screenshot:
            screenshots.append(f"null-backend://{spec.name}.png")

        return BrowserCheckResult(
            passed=passed,
            screenshots=screenshots,
            console_errors=[],
            failed_assertions=failed_assertions,
            duration_ms=0,
        )


def _assertion_passes(assertion: BrowserAssertion) -> bool:
    """An assertion passes unless its value is empty/whitespace (deterministic)."""
    return bool(assertion.value.strip())
