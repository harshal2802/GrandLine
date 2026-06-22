"""Factory for creating Bedside Browser backends.

Mirrors ``app.execution.factory`` / the deployment backend selection: selects the
backend on the ``browser_backend`` setting (env ``GRANDLINE_BROWSER_BACKEND``).
The default is ``"null"`` (deterministic, browser-free, CI-safe); ``"playwright"``
opts into the real backend. An unknown value raises ``ValueError``.
"""

from __future__ import annotations

from typing import Any

from app.browser.backend import BrowserCheckBackend


def create_browser_backend(settings: Any) -> BrowserCheckBackend:
    name = getattr(settings, "browser_backend", "null")
    if name == "null":
        from app.browser.null_backend import NullBrowserBackend

        return NullBrowserBackend()
    if name == "playwright":
        from app.browser.playwright_backend import PlaywrightBrowserBackend

        return PlaywrightBrowserBackend()
    raise ValueError(f"Unknown browser backend: {name}")
