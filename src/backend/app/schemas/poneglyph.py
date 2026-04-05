import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class PoneglyphRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    voyage_id: uuid.UUID
    phase_number: int
    content: str
    metadata_: dict[str, Any] | None
    created_by: str
    created_at: datetime
