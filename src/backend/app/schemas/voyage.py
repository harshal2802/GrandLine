import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import VoyageStatus


class VoyageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    target_repo: str | None = Field(default=None, max_length=500)


class VoyageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    description: str | None
    status: VoyageStatus
    target_repo: str | None
    created_at: datetime
    updated_at: datetime


class VoyagePlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    voyage_id: uuid.UUID
    phases: dict[str, Any]
    created_by: str
    version: int
    created_at: datetime
