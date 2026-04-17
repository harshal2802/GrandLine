import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BuildArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    voyage_id: uuid.UUID
    shipwright_run_id: uuid.UUID
    phase_number: int
    file_path: str
    content: str
    language: str
    created_by: str
    created_at: datetime
