import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class HealthCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    voyage_id: uuid.UUID
    poneglyph_id: uuid.UUID | None
    phase_number: int
    file_path: str
    content: str
    framework: str
    last_run_status: str | None
    last_run_output: str | None
    last_run_at: datetime | None
    metadata_: dict[str, Any] | None
    created_by: str
    created_at: datetime
