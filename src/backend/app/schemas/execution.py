import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ExecutionRequest(BaseModel):
    command: str
    working_dir: str = "/workspace"
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    environment: dict[str, str] = Field(default_factory=dict)
    files: dict[str, str] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_seconds: float
    sandbox_id: str


class SandboxStatus(BaseModel):
    sandbox_id: str
    state: Literal["running", "idle", "destroyed"]
    user_id: uuid.UUID
    created_at: datetime
