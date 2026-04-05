import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DialConfigCreate(BaseModel):
    voyage_id: uuid.UUID
    role_mapping: dict[str, Any]
    fallback_chain: dict[str, Any] | None = None


class DialConfigUpdate(BaseModel):
    role_mapping: dict[str, Any] | None = None
    fallback_chain: dict[str, Any] | None = None


class DialConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    voyage_id: uuid.UUID
    role_mapping: dict[str, Any]
    fallback_chain: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
