"""Tests for Captain Agent Pydantic schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.enums import CrewRole
from app.schemas.captain import (
    ChartCourseRequest,
    PhaseSpec,
    VoyagePlanSpec,
)


class TestPhaseSpec:
    def test_valid_phase(self) -> None:
        phase = PhaseSpec(
            phase_number=1,
            name="Design architecture",
            description="Create system architecture document",
            assigned_to=CrewRole.NAVIGATOR,
            depends_on=[],
            artifacts=["architecture.md"],
        )
        assert phase.phase_number == 1
        assert phase.assigned_to == CrewRole.NAVIGATOR

    def test_rejects_phase_number_zero(self) -> None:
        with pytest.raises(ValidationError):
            PhaseSpec(
                phase_number=0,
                name="Bad phase",
                description="Invalid",
                assigned_to=CrewRole.NAVIGATOR,
            )

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValidationError):
            PhaseSpec(
                phase_number=1,
                name="",
                description="Valid description",
                assigned_to=CrewRole.NAVIGATOR,
            )

    def test_defaults(self) -> None:
        phase = PhaseSpec(
            phase_number=1,
            name="Test",
            description="Test desc",
            assigned_to=CrewRole.SHIPWRIGHT,
        )
        assert phase.depends_on == []
        assert phase.artifacts == []


class TestVoyagePlanSpec:
    def test_rejects_empty_phases(self) -> None:
        with pytest.raises(ValidationError):
            VoyagePlanSpec(phases=[])

    def test_rejects_circular_deps(self) -> None:
        with pytest.raises(ValidationError, match="circular"):
            VoyagePlanSpec(
                phases=[
                    PhaseSpec(
                        phase_number=1,
                        name="A",
                        description="Phase A",
                        assigned_to=CrewRole.NAVIGATOR,
                        depends_on=[2],
                    ),
                    PhaseSpec(
                        phase_number=2,
                        name="B",
                        description="Phase B",
                        assigned_to=CrewRole.SHIPWRIGHT,
                        depends_on=[1],
                    ),
                ]
            )

    def test_rejects_self_dependency(self) -> None:
        with pytest.raises(ValidationError, match="circular"):
            VoyagePlanSpec(
                phases=[
                    PhaseSpec(
                        phase_number=1,
                        name="Self",
                        description="Self dep",
                        assigned_to=CrewRole.NAVIGATOR,
                        depends_on=[1],
                    ),
                ]
            )

    def test_rejects_duplicate_phase_numbers(self) -> None:
        with pytest.raises(ValidationError, match="Duplicate phase_number 1"):
            VoyagePlanSpec(
                phases=[
                    PhaseSpec(
                        phase_number=1,
                        name="First",
                        description="First phase",
                        assigned_to=CrewRole.NAVIGATOR,
                    ),
                    PhaseSpec(
                        phase_number=1,
                        name="Duplicate",
                        description="Same number",
                        assigned_to=CrewRole.SHIPWRIGHT,
                    ),
                ]
            )

    def test_rejects_nonexistent_dependency(self) -> None:
        with pytest.raises(ValidationError, match="non-existent phase 99"):
            VoyagePlanSpec(
                phases=[
                    PhaseSpec(
                        phase_number=1,
                        name="Only",
                        description="Only phase",
                        assigned_to=CrewRole.NAVIGATOR,
                        depends_on=[99],
                    ),
                ]
            )

    def test_accepts_valid_dag(self) -> None:
        plan = VoyagePlanSpec(
            phases=[
                PhaseSpec(
                    phase_number=1,
                    name="Design",
                    description="Architecture",
                    assigned_to=CrewRole.NAVIGATOR,
                ),
                PhaseSpec(
                    phase_number=2,
                    name="Implement",
                    description="Code it",
                    assigned_to=CrewRole.SHIPWRIGHT,
                    depends_on=[1],
                ),
                PhaseSpec(
                    phase_number=3,
                    name="Test",
                    description="Write tests",
                    assigned_to=CrewRole.DOCTOR,
                    depends_on=[1, 2],
                ),
            ]
        )
        assert len(plan.phases) == 3


class TestChartCourseRequest:
    def test_rejects_short_task(self) -> None:
        with pytest.raises(ValidationError):
            ChartCourseRequest(task="short")

    def test_rejects_long_task(self) -> None:
        with pytest.raises(ValidationError):
            ChartCourseRequest(task="x" * 5001)

    def test_accepts_valid_task(self) -> None:
        req = ChartCourseRequest(task="Build a REST API for user authentication with JWT tokens")
        assert len(req.task) >= 10
