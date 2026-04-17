"""Schemas for Doctor Agent (QA)."""

from __future__ import annotations

import posixpath
import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.health_check import HealthCheckRead


def _validate_relative_path(path: str) -> str:
    """Reject absolute paths and path-traversal segments."""
    if path.startswith("/") or path.startswith("\\"):
        raise ValueError(f"Path must be relative, got {path!r}")
    if ":" in path.split("/")[0]:
        raise ValueError(f"Path must not be a drive/scheme, got {path!r}")
    normalized = posixpath.normpath(path)
    if normalized.startswith("..") or "/../" in f"/{normalized}/":
        raise ValueError(f"Path traversal not allowed in {path!r}")
    if normalized in (".", ""):
        raise ValueError(f"Path must not be empty, got {path!r}")
    return path


class HealthCheckSpec(BaseModel):
    """Structured content the LLM generates for one health check test file."""

    phase_number: int = Field(ge=1)
    file_path: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    framework: Literal["pytest", "vitest"] = "pytest"

    @field_validator("file_path")
    @classmethod
    def _validate_file_path(cls, v: str) -> str:
        return _validate_relative_path(v)


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

    @field_validator("files")
    @classmethod
    def _validate_file_paths(cls, v: dict[str, str]) -> dict[str, str]:
        for path in v:
            _validate_relative_path(path)
        return v


class ValidationResultResponse(BaseModel):
    voyage_id: uuid.UUID
    status: Literal["passed", "failed"]
    passed_count: int
    failed_count: int
    total_count: int
    summary: str
