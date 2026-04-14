"""Schemas for Captain Agent (Project Manager)."""

from __future__ import annotations

import uuid
from collections import deque
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import CrewRole


class PhaseSpec(BaseModel):
    phase_number: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=200)
    description: str
    assigned_to: CrewRole
    depends_on: list[int] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


class VoyagePlanSpec(BaseModel):
    phases: list[PhaseSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_no_circular_deps(self) -> VoyagePlanSpec:
        """Topological sort to reject circular dependencies."""
        phase_nums = {p.phase_number for p in self.phases}
        adj: dict[int, list[int]] = {p.phase_number: [] for p in self.phases}
        in_degree: dict[int, int] = {p.phase_number: 0 for p in self.phases}

        for p in self.phases:
            for dep in p.depends_on:
                if dep not in phase_nums:
                    continue
                adj[dep].append(p.phase_number)
                in_degree[p.phase_number] += 1

        queue: deque[int] = deque(n for n, d in in_degree.items() if d == 0)
        visited = 0
        while queue:
            node = queue.popleft()
            visited += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(phase_nums):
            raise ValueError("Voyage plan has circular dependencies between phases")
        return self


class ChartCourseRequest(BaseModel):
    task: str = Field(min_length=10, max_length=5000)


class ChartCourseResponse(BaseModel):
    voyage_id: uuid.UUID
    plan_id: uuid.UUID
    plan: VoyagePlanSpec
    version: int


class VoyagePlanResponse(BaseModel):
    plan_id: uuid.UUID
    voyage_id: uuid.UUID
    phases: list[PhaseSpec]
    version: int
    created_by: str
    created_at: datetime
