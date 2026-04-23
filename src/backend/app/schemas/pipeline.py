"""Schemas for the master Voyage Pipeline."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict


class PipelineStatusSnapshot(BaseModel):
    """Read-model returned by PipelineService.get_status."""

    model_config = ConfigDict(strict=True)

    voyage_id: uuid.UUID
    status: str
    plan_exists: bool
    poneglyph_count: int
    health_check_count: int
    build_artifact_count: int
    phase_status: dict[str, str]
    last_validation_status: str | None
    last_deployment_status: str | None
    error: dict[str, Any] | None
