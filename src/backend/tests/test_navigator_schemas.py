"""Tests for Navigator Agent Pydantic schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.navigator import (
    NavigatorOutputSpec,
    PoneglyphContentSpec,
)


class TestPoneglyphContentSpec:
    def test_valid_spec(self) -> None:
        spec = PoneglyphContentSpec(
            phase_number=1,
            title="Design API schema",
            task_description="Create OpenAPI schema for user endpoints",
            technical_constraints=["Must use Pydantic v2"],
            expected_inputs=["Requirements document"],
            expected_outputs=["openapi.yaml"],
            test_criteria=["Schema validates against OpenAPI 3.1 spec"],
            file_paths=["src/schemas/user.py"],
            implementation_notes="Use FastAPI auto-generation",
        )
        assert spec.phase_number == 1
        assert spec.title == "Design API schema"

    def test_rejects_phase_number_zero(self) -> None:
        with pytest.raises(ValidationError):
            PoneglyphContentSpec(
                phase_number=0,
                title="Bad phase",
                task_description="Invalid",
                test_criteria=["something"],
            )

    def test_rejects_empty_title(self) -> None:
        with pytest.raises(ValidationError):
            PoneglyphContentSpec(
                phase_number=1,
                title="",
                task_description="Valid description",
                test_criteria=["something"],
            )

    def test_rejects_empty_test_criteria(self) -> None:
        with pytest.raises(ValidationError):
            PoneglyphContentSpec(
                phase_number=1,
                title="Valid title",
                task_description="Valid description",
                test_criteria=[],
            )

    def test_defaults(self) -> None:
        spec = PoneglyphContentSpec(
            phase_number=1,
            title="Minimal",
            task_description="Minimal description",
            test_criteria=["At least one criterion"],
        )
        assert spec.technical_constraints == []
        assert spec.expected_inputs == []
        assert spec.expected_outputs == []
        assert spec.file_paths == []
        assert spec.implementation_notes == ""


class TestNavigatorOutputSpec:
    def test_rejects_empty_poneglyphs(self) -> None:
        with pytest.raises(ValidationError):
            NavigatorOutputSpec(poneglyphs=[])

    def test_rejects_duplicate_phase_numbers(self) -> None:
        with pytest.raises(ValidationError, match="Duplicate phase_number 1"):
            NavigatorOutputSpec(
                poneglyphs=[
                    PoneglyphContentSpec(
                        phase_number=1,
                        title="First",
                        task_description="First phase",
                        test_criteria=["test A"],
                    ),
                    PoneglyphContentSpec(
                        phase_number=1,
                        title="Duplicate",
                        task_description="Same number",
                        test_criteria=["test B"],
                    ),
                ]
            )

    def test_accepts_valid_multi_phase(self) -> None:
        output = NavigatorOutputSpec(
            poneglyphs=[
                PoneglyphContentSpec(
                    phase_number=1,
                    title="Design",
                    task_description="Architecture",
                    test_criteria=["Has diagram"],
                ),
                PoneglyphContentSpec(
                    phase_number=2,
                    title="Implement",
                    task_description="Write code",
                    test_criteria=["Tests pass"],
                ),
            ]
        )
        assert len(output.poneglyphs) == 2
