"""BrowserCheckBackend ABC — the swappable seam for the Bedside Browser.

Mirrors ``ExecutionBackend`` / ``DeploymentBackend``: a clean async ABC behind a
factory so a real browser can be swapped in without the service layer ever
importing a browser library. The v1 default (``NullBrowserBackend``) needs no
browser at all, keeping CI and the test suite browser-free.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.browser_check import BrowserCheckResult, BrowserCheckSpec


class BrowserBackendError(Exception):
    """Raised for backend-internal errors only (e.g. Playwright not installed,
    a browser launch failure). A check that simply fails its assertions returns
    ``BrowserCheckResult(passed=False, ...)`` rather than raising."""


class BrowserCheckBackend(ABC):
    @abstractmethod
    async def run(self, spec: BrowserCheckSpec) -> BrowserCheckResult:
        """Drive a browser through the spec and return the rendered outcome."""
        ...

    async def close(self) -> None:
        """Release resources (e.g. a launched browser / Playwright process)."""
