"""Schemas for Navigator Agent (Architect)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, model_validator

from app.schemas.poneglyph import PoneglyphRead


class PoneglyphContentSpec(BaseModel):
    """Structured content the LLM generates for one phase."""

    phase_number: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    task_description: str = Field(min_length=1)
    technical_constraints: list[str] = Field(default_factory=list)
    expected_inputs: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    test_criteria: list[str] = Field(min_length=1)
    file_paths: list[str] = Field(default_factory=list)
    implementation_notes: str = ""


class NavigatorOutputSpec(BaseModel):
    """Full LLM output: poneglyphs for all phases."""

    poneglyphs: list[PoneglyphContentSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_phases(self) -> NavigatorOutputSpec:
        """Reject duplicate phase_number values."""
        phase_nums = [p.phase_number for p in self.poneglyphs]
        if len(phase_nums) != len(set(phase_nums)):
            seen: set[int] = set()
            for n in phase_nums:
                if n in seen:
                    raise ValueError(f"Duplicate phase_number {n}")
                seen.add(n)
        return self


class DraftPoneglyphsRequest(BaseModel):
    """Empty body — plan is fetched from DB internally."""


class DraftPoneglyphsResponse(BaseModel):
    voyage_id: uuid.UUID
    poneglyph_ids: list[uuid.UUID]
    count: int


class PoneglyphListResponse(BaseModel):
    voyage_id: uuid.UUID
    poneglyphs: list[PoneglyphRead]
