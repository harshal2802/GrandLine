"""Schemas for Doctor Agent (QA)."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.health_check import HealthCheckRead


class HealthCheckSpec(BaseModel):
    """Structured content the LLM generates for one health check test file."""

    phase_number: int = Field(ge=1)
    file_path: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    framework: Literal["pytest", "vitest"] = "pytest"


class DoctorOutputSpec(BaseModel):
    """Full LLM output: health checks for all phases."""

    health_checks: list[HealthCheckSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_file_paths(self) -> DoctorOutputSpec:
        """Reject duplicate file_path values."""
        paths = [hc.file_path for hc in self.health_checks]
        if len(paths) != len(set(paths)):
            seen: set[str] = set()
            for p in paths:
                if p in seen:
                    raise ValueError(f"Duplicate file_path {p!r}")
                seen.add(p)
        return self


class WriteHealthChecksResponse(BaseModel):
    voyage_id: uuid.UUID
    health_check_ids: list[uuid.UUID]
    count: int


class HealthCheckListResponse(BaseModel):
    voyage_id: uuid.UUID
    health_checks: list[HealthCheckRead]


class ValidateCodeRequest(BaseModel):
    files: dict[str, str] = Field(min_length=1)


class ValidationResultResponse(BaseModel):
    voyage_id: uuid.UUID
    status: Literal["passed", "failed"]
    passed_count: int
    failed_count: int
    total_count: int
    summary: str
