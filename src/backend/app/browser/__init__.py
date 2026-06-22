"""Bedside Browser (Phase 23) — swappable browser-check backends.

Real browser execution sits behind a clean ``BrowserCheckBackend`` ABC selected
by a factory, exactly like ``ExecutionBackend`` / ``DeploymentBackend``. The v1
default is the deterministic ``NullBrowserBackend`` (no real browser, CI-safe);
``PlaywrightBrowserBackend`` is the opt-in real backend, lazily importing
Playwright so app startup and the test suite never require it.
"""

from app.browser.backend import (
    BrowserBackendError,
    BrowserCheckBackend,
)
from app.browser.factory import create_browser_backend
from app.browser.null_backend import NullBrowserBackend
from app.browser.playwright_backend import PlaywrightBrowserBackend

__all__ = [
    "BrowserBackendError",
    "BrowserCheckBackend",
    "NullBrowserBackend",
    "PlaywrightBrowserBackend",
    "create_browser_backend",
]
