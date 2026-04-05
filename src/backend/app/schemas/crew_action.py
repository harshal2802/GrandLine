import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CrewActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    voyage_id: uuid.UUID
    crew_member: str
    action_type: str
    summary: str
    details: dict[str, Any] | None
    created_at: datetime
