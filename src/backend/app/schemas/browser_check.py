"""Schemas for the Bedside Browser (Phase 23) — browser-in-the-loop verification.

The Doctor's Bedside Browser drives a headless browser against a running app and
asserts the page actually renders ("tests pass AND the page renders"). The spec
describes WHAT to check; the result captures the outcome plus an opaque
screenshot ref the Ship's Log surfaces. Real browser execution sits behind a
swappable ``BrowserCheckBackend`` so these schemas never depend on a browser.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BrowserAssertion(BaseModel):
    """A single thing the Doctor asserts about the rendered page."""

    type: Literal["selector_present", "text_present"]
    value: str = Field(min_length=0, max_length=2000)


class BrowserCheckSpec(BaseModel):
    """The browser health check to run against a running app."""

    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=2000)
    wait_for: str | None = Field(default=None, max_length=2000)
    assertions: list[BrowserAssertion] = Field(default_factory=list)
    capture_screenshot: bool = True


class BrowserCheckResult(BaseModel):
    """The outcome of running a ``BrowserCheckSpec`` through a backend.

    ``screenshots`` carry opaque refs (e.g. ``null-backend://<name>.png``) — the
    Ship's Log surfaces them; how they resolve is the backend's concern.
    """

    passed: bool
    screenshots: list[str] = Field(default_factory=list)
    console_errors: list[str] = Field(default_factory=list)
    failed_assertions: list[str] = Field(default_factory=list)
    duration_ms: int = Field(ge=0)


class BrowserCheckRead(BaseModel):
    """DB row read model for a persisted ``BrowserCheck``."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    voyage_id: uuid.UUID
    phase_number: int | None
    url: str
    passed: bool
    screenshot_ref: str | None
    console_errors: list[str]
    failed_assertions: list[str]
    created_at: datetime
