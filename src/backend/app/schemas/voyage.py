import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import VoyageStatus


class VoyageCreate(BaseModel):
    title: str
    description: str | None = None
    target_repo: str | None = None


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
