"""Schemas for the Observation Deck REST endpoints.

Phase 16.0. ``nextCursor`` is camelCase deliberately: the frontend treats it
as opaque and the JSON stays JS-idiomatic.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CrewActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    voyage_id: uuid.UUID
    crew_member: str
    action_type: str
    summary: str
    details: dict[str, Any] | None
    created_at: datetime


class CrewActionListResponse(BaseModel):
    items: list[CrewActionRead]
    next_cursor: str | None = Field(
        default=None, alias="nextCursor", serialization_alias="nextCursor"
    )

    model_config = ConfigDict(populate_by_name=True)


class VoyageListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    status: str
    target_repo: str | None
    phase_status: dict[str, str]
    created_at: datetime
    updated_at: datetime


class VoyageListResponse(BaseModel):
    items: list[VoyageListItem]
    next_cursor: str | None = Field(
        default=None, alias="nextCursor", serialization_alias="nextCursor"
    )

    model_config = ConfigDict(populate_by_name=True)


__all__ = [
    "CrewActionListResponse",
    "CrewActionRead",
    "VoyageListItem",
    "VoyageListResponse",
]
