"""Schemas for the Log Book — per-repo cross-voyage memory."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Locked taxonomy for a Log Book entry's ``kind``. Anything else is rejected at
# the schema boundary so the recall surface stays predictable.
LogBookKind = Literal["convention", "decision", "layout", "gotcha", "summary"]


class LogBookEntryCreate(BaseModel):
    """Payload for recording a new piece of prior knowledge for a repo."""

    repo: str = Field(min_length=1, max_length=500)
    author: str = Field(min_length=1, max_length=50)
    kind: LogBookKind
    content: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)
    voyage_id: uuid.UUID | None = None


class LogBookEntryRead(BaseModel):
    """A Log Book entry as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repo: str
    voyage_id: uuid.UUID | None
    author: str
    kind: str
    content: str
    details: dict[str, Any]
    created_at: datetime


class RecalledContext(BaseModel):
    """The Log Book knowledge the Captain recalls for a repo at planning time."""

    repo: str
    entries: list[LogBookEntryRead] = Field(default_factory=list)
    rendered: str = ""
