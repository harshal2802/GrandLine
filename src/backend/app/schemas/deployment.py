"""Schemas for Helmsman Agent (DevOps)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DeploymentTier = Literal["preview", "staging", "production"]
DeploymentAction = Literal["deploy", "rollback"]
DeploymentStatus = Literal["running", "completed", "failed"]


class DeploymentDiagnosisSpec(BaseModel):
    """Structured LLM diagnosis of a deployment failure."""

    summary: str = Field(min_length=1, max_length=500)
    likely_cause: str = Field(min_length=1, max_length=1000)
    suggested_action: str = Field(min_length=1, max_length=1000)


class DeployRequest(BaseModel):
    tier: DeploymentTier
    git_ref: str | None = Field(default=None, max_length=255)
    approved_by: uuid.UUID | None = None


class RollbackRequest(BaseModel):
    tier: DeploymentTier


class DeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    voyage_id: uuid.UUID
    tier: DeploymentTier
    action: DeploymentAction
    git_ref: str
    git_sha: str | None
    status: DeploymentStatus
    approved_by: uuid.UUID | None
    url: str | None
    backend_log: str | None
    diagnosis: dict[str, Any] | None
    previous_deployment_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class DeploymentResponse(BaseModel):
    voyage_id: uuid.UUID
    deployment_id: uuid.UUID
    tier: DeploymentTier
    action: DeploymentAction
    status: DeploymentStatus
    git_ref: str
    git_sha: str | None
    url: str | None
    diagnosis: dict[str, Any] | None


class DeploymentListResponse(BaseModel):
    voyage_id: uuid.UUID
    tier: DeploymentTier | None
    deployments: list[DeploymentRead]
