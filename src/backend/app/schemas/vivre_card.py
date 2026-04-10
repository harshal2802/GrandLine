import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import CheckpointReason, CrewRole


class VivreCardCreate(BaseModel):
    crew_member: CrewRole
    state_data: dict[str, Any]
    checkpoint_reason: CheckpointReason


class VivreCardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    voyage_id: uuid.UUID
    crew_member: str
    state_data: dict[str, Any]
    checkpoint_reason: str
    created_at: datetime


class VivreCardList(BaseModel):
    items: list[VivreCardRead]
    total: int
    limit: int
    offset: int


class VivreCardDiff(BaseModel):
    card_a_id: uuid.UUID
    card_b_id: uuid.UUID
    added: dict[str, Any]
    removed: dict[str, Any]
    changed: dict[str, dict[str, Any]]


class VivreCardRestore(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    card_id: uuid.UUID
    voyage_id: uuid.UUID
    crew_member: str
    state_data: dict[str, Any]
    checkpoint_reason: str
    restored_at: datetime


class CleanupResult(BaseModel):
    deleted_count: int
    kept_count: int
    voyage_id: uuid.UUID
