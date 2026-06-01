"""Schemas for the master Voyage Pipeline."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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


class StartVoyageRequest(BaseModel):
    """POST /voyages/{id}/start request body."""

    model_config = ConfigDict(strict=True, extra="forbid")

    task: str = Field(min_length=10, max_length=5000)
    deploy_tier: Literal["preview"] = "preview"
    max_parallel_shipwrights: int | None = Field(default=None, ge=1, le=10)


class InjectContextRequest(BaseModel):
    """POST /voyages/{id}/inject request body (Phase 17)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    context: str = Field(min_length=1, max_length=5000)
    phase_number: int | None = Field(default=None, ge=0)


class RedirectPhaseRequest(BaseModel):
    """POST /voyages/{id}/redirect request body (Phase 17)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    phase_number: int = Field(ge=0)
    instruction: str = Field(min_length=1, max_length=5000)


class InterventionResponse(BaseModel):
    """Response envelope for inject/redirect interventions."""

    model_config = ConfigDict(strict=True)

    voyage_id: uuid.UUID
    crew_action_id: uuid.UUID
    status: str


class StartVoyageResponse(BaseModel):
    """POST /voyages/{id}/start 202 response envelope."""

    model_config = ConfigDict(strict=True)

    voyage_id: uuid.UUID
    status: str  # voyage.status at the moment of acceptance
    accepted: bool = True


class PipelineEventEnvelope(BaseModel):
    """Wire envelope sent over SSE for each Redis stream message."""

    model_config = ConfigDict(strict=True)

    msg_id: str  # Redis stream message id (for client dedup)
    event: dict[str, Any]  # parsed event JSON (event_type, voyage_id, payload, ...)
