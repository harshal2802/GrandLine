"""Schemas for Shipwright Agent (Developer)."""

from __future__ import annotations

import posixpath
import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.build_artifact import BuildArtifactRead


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


class BuildArtifactSpec(BaseModel):
    """Structured content the LLM generates for one source file."""

    file_path: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    language: Literal["python", "typescript", "javascript"] = "python"

    @field_validator("file_path")
    @classmethod
    def _validate_file_path(cls, v: str) -> str:
        return _validate_relative_path(v)


class ShipwrightOutputSpec(BaseModel):
    """Full LLM output: one or more source files for a single phase."""

    files: list[BuildArtifactSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_file_paths(self) -> ShipwrightOutputSpec:
        paths = [f.file_path for f in self.files]
        if len(paths) != len(set(paths)):
            seen: set[str] = set()
            for p in paths:
                if p in seen:
                    raise ValueError(f"Duplicate file_path {p!r}")
                seen.add(p)
        return self


class BuildResultResponse(BaseModel):
    voyage_id: uuid.UUID
    phase_number: int
    shipwright_run_id: uuid.UUID
    status: Literal["passed", "failed", "max_iterations"]
    iteration_count: int
    passed_count: int
    failed_count: int
    total_count: int
    file_count: int
    summary: str


class BuildArtifactListResponse(BaseModel):
    voyage_id: uuid.UUID
    phase_number: int | None
    artifacts: list[BuildArtifactRead]
