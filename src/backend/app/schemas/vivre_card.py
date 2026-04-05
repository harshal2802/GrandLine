import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import CheckpointReason, CrewRole


class VivreCardCreate(BaseModel):
    voyage_id: uuid.UUID
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
