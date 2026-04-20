"""Tests for pipeline transition guards."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.models.enums import VoyageStatus
from app.services.pipeline_guards import (
    PipelineError,
    require_can_enter_building,
    require_can_enter_deploying,
    require_can_enter_pdd,
    require_can_enter_planning,
    require_can_enter_reviewing,
    require_can_enter_tdd,
)
from app.services.shipwright_service import (
    PHASE_STATUS_BUILDING,
    PHASE_STATUS_BUILT,
    PHASE_STATUS_FAILED,
)


def _mock_voyage(
    status: str = VoyageStatus.CHARTED.value,
    phase_status: dict[str, str] | None = None,
) -> MagicMock:
    voyage = MagicMock()
    voyage.status = status
    voyage.phase_status = phase_status if phase_status is not None else {}
    return voyage


def _mock_plan(phase_numbers: list[int]) -> MagicMock:
    plan = MagicMock()
    plan.phases = {
        "phases": [
            {
                "phase_number": n,
                "name": f"phase {n}",
                "description": "do the thing",
                "assigned_to": "shipwright",
                "depends_on": [],
                "artifacts": [],
            }
            for n in phase_numbers
        ]
    }
    return plan


def _mock_poneglyph(phase_number: int) -> MagicMock:
    p = MagicMock()
    p.phase_number = phase_number
    return p


def _mock_health_check(phase_number: int) -> MagicMock:
    hc = MagicMock()
    hc.phase_number = phase_number
    return hc


def _mock_artifact(phase_number: int) -> MagicMock:
    a = MagicMock()
    a.phase_number = phase_number
    return a


def _mock_validation(status_: str) -> MagicMock:
    v = MagicMock()
    v.status = status_
    return v


class TestPipelineError:
    def test_init_sets_code_and_message(self) -> None:
        err = PipelineError("CODE_X", "something went wrong")
        assert err.code == "CODE_X"
        assert err.message == "something went wrong"

    def test_is_exception(self) -> None:
        assert isinstance(PipelineError("X", "msg"), Exception)

    def test_str_shows_message(self) -> None:
        err = PipelineError("X", "boom")
        assert "boom" in str(err)


class TestRequireCanEnterPlanning:
    def test_allows_charted(self) -> None:
        require_can_enter_planning(_mock_voyage(status=VoyageStatus.CHARTED.value))

    def test_allows_paused(self) -> None:
        require_can_enter_planning(_mock_voyage(status=VoyageStatus.PAUSED.value))

    def test_allows_failed(self) -> None:
        require_can_enter_planning(_mock_voyage(status=VoyageStatus.FAILED.value))

    def test_rejects_completed(self) -> None:
        with pytest.raises(PipelineError) as exc:
            require_can_enter_planning(_mock_voyage(status=VoyageStatus.COMPLETED.value))
        assert exc.value.code == "VOYAGE_NOT_PLANNABLE"

    def test_rejects_planning(self) -> None:
        with pytest.raises(PipelineError) as exc:
            require_can_enter_planning(_mock_voyage(status=VoyageStatus.PLANNING.value))
        assert exc.value.code == "VOYAGE_NOT_PLANNABLE"

    def test_rejects_cancelled(self) -> None:
        with pytest.raises(PipelineError) as exc:
            require_can_enter_planning(_mock_voyage(status=VoyageStatus.CANCELLED.value))
        assert exc.value.code == "VOYAGE_NOT_PLANNABLE"


class TestRequireCanEnterPdd:
    def test_allows_when_plan_exists(self) -> None:
        require_can_enter_pdd(_mock_voyage(), _mock_plan([1]))

    def test_rejects_when_plan_is_none(self) -> None:
        with pytest.raises(PipelineError) as exc:
            require_can_enter_pdd(_mock_voyage(), None)
        assert exc.value.code == "PLAN_MISSING"


class TestRequireCanEnterTdd:
    def test_allows_when_every_phase_has_poneglyph(self) -> None:
        plan = _mock_plan([1, 2])
        require_can_enter_tdd(_mock_voyage(), plan, [_mock_poneglyph(1), _mock_poneglyph(2)])

    def test_rejects_when_any_phase_missing_poneglyph(self) -> None:
        plan = _mock_plan([1, 2, 3])
        with pytest.raises(PipelineError) as exc:
            require_can_enter_tdd(_mock_voyage(), plan, [_mock_poneglyph(1), _mock_poneglyph(3)])
        assert exc.value.code == "PONEGLYPHS_INCOMPLETE"

    def test_rejects_when_no_poneglyphs_at_all(self) -> None:
        plan = _mock_plan([1, 2])
        with pytest.raises(PipelineError) as exc:
            require_can_enter_tdd(_mock_voyage(), plan, [])
        assert exc.value.code == "PONEGLYPHS_INCOMPLETE"

    def test_message_lists_missing_phase_numbers(self) -> None:
        plan = _mock_plan([1, 2, 3])
        with pytest.raises(PipelineError) as exc:
            require_can_enter_tdd(_mock_voyage(), plan, [_mock_poneglyph(1)])
        assert "2" in exc.value.message
        assert "3" in exc.value.message

    def test_ignores_extra_poneglyphs_for_phases_not_in_plan(self) -> None:
        plan = _mock_plan([1, 2])
        require_can_enter_tdd(
            _mock_voyage(),
            plan,
            [_mock_poneglyph(1), _mock_poneglyph(2), _mock_poneglyph(99)],
        )


class TestRequireCanEnterBuilding:
    def test_allows_when_every_phase_has_health_check(self) -> None:
        plan = _mock_plan([1, 2])
        require_can_enter_building(
            _mock_voyage(), plan, [_mock_health_check(1), _mock_health_check(2)]
        )

    def test_rejects_when_any_phase_missing_health_check(self) -> None:
        plan = _mock_plan([1, 2])
        with pytest.raises(PipelineError) as exc:
            require_can_enter_building(_mock_voyage(), plan, [_mock_health_check(1)])
        assert exc.value.code == "HEALTH_CHECKS_INCOMPLETE"

    def test_rejects_when_no_health_checks(self) -> None:
        plan = _mock_plan([1, 2])
        with pytest.raises(PipelineError) as exc:
            require_can_enter_building(_mock_voyage(), plan, [])
        assert exc.value.code == "HEALTH_CHECKS_INCOMPLETE"

    def test_message_lists_missing_phase_numbers(self) -> None:
        plan = _mock_plan([1, 2, 3])
        with pytest.raises(PipelineError) as exc:
            require_can_enter_building(_mock_voyage(), plan, [_mock_health_check(2)])
        assert "1" in exc.value.message
        assert "3" in exc.value.message

    def test_multiple_health_checks_per_phase_counts_as_covered(self) -> None:
        plan = _mock_plan([1, 2])
        require_can_enter_building(
            _mock_voyage(),
            plan,
            [
                _mock_health_check(1),
                _mock_health_check(1),
                _mock_health_check(1),
                _mock_health_check(2),
            ],
        )


class TestRequireCanEnterReviewing:
    def test_allows_when_all_phases_built_with_artifacts(self) -> None:
        plan = _mock_plan([1, 2])
        voyage = _mock_voyage(phase_status={"1": PHASE_STATUS_BUILT, "2": PHASE_STATUS_BUILT})
        require_can_enter_reviewing(voyage, plan, [_mock_artifact(1), _mock_artifact(2)])

    def test_rejects_when_artifact_missing_for_phase(self) -> None:
        plan = _mock_plan([1, 2])
        voyage = _mock_voyage(phase_status={"1": PHASE_STATUS_BUILT, "2": PHASE_STATUS_BUILT})
        with pytest.raises(PipelineError) as exc:
            require_can_enter_reviewing(voyage, plan, [_mock_artifact(1)])
        assert exc.value.code == "BUILD_INCOMPLETE"

    def test_rejects_when_phase_status_building(self) -> None:
        plan = _mock_plan([1, 2])
        voyage = _mock_voyage(phase_status={"1": PHASE_STATUS_BUILT, "2": PHASE_STATUS_BUILDING})
        with pytest.raises(PipelineError) as exc:
            require_can_enter_reviewing(voyage, plan, [_mock_artifact(1), _mock_artifact(2)])
        assert exc.value.code == "BUILD_INCOMPLETE"

    def test_rejects_when_phase_status_failed(self) -> None:
        plan = _mock_plan([1, 2])
        voyage = _mock_voyage(phase_status={"1": PHASE_STATUS_BUILT, "2": PHASE_STATUS_FAILED})
        with pytest.raises(PipelineError) as exc:
            require_can_enter_reviewing(voyage, plan, [_mock_artifact(1), _mock_artifact(2)])
        assert exc.value.code == "BUILD_INCOMPLETE"

    def test_rejects_when_phase_status_missing_for_phase(self) -> None:
        plan = _mock_plan([1, 2])
        voyage = _mock_voyage(phase_status={"1": PHASE_STATUS_BUILT})
        with pytest.raises(PipelineError) as exc:
            require_can_enter_reviewing(voyage, plan, [_mock_artifact(1), _mock_artifact(2)])
        assert exc.value.code == "BUILD_INCOMPLETE"

    def test_message_lists_missing_phase_numbers(self) -> None:
        plan = _mock_plan([1, 2, 3])
        voyage = _mock_voyage(
            phase_status={
                "1": PHASE_STATUS_BUILT,
                "2": PHASE_STATUS_FAILED,
                "3": PHASE_STATUS_BUILT,
            }
        )
        with pytest.raises(PipelineError) as exc:
            require_can_enter_reviewing(
                voyage,
                plan,
                [_mock_artifact(1), _mock_artifact(2), _mock_artifact(3)],
            )
        assert "2" in exc.value.message


class TestRequireCanEnterDeploying:
    def test_allows_when_latest_validation_passed(self) -> None:
        require_can_enter_deploying(_mock_voyage(), _mock_validation("passed"))

    def test_rejects_when_latest_validation_is_none(self) -> None:
        with pytest.raises(PipelineError) as exc:
            require_can_enter_deploying(_mock_voyage(), None)
        assert exc.value.code == "VALIDATION_NOT_PASSED"

    def test_rejects_when_latest_validation_failed(self) -> None:
        with pytest.raises(PipelineError) as exc:
            require_can_enter_deploying(_mock_voyage(), _mock_validation("failed"))
        assert exc.value.code == "VALIDATION_NOT_PASSED"

    def test_rejects_when_latest_validation_has_unknown_status(self) -> None:
        with pytest.raises(PipelineError) as exc:
            require_can_enter_deploying(_mock_voyage(), _mock_validation("weird"))
        assert exc.value.code == "VALIDATION_NOT_PASSED"


class TestPlanWithMalformedPhases:
    """Plan coming from DB is a dict — Pydantic parse must succeed for well-formed plans."""

    def test_tdd_guard_parses_real_plan_dict_shape(self) -> None:
        plan = MagicMock()
        plan.phases = {
            "phases": [
                {
                    "phase_number": 1,
                    "name": "a",
                    "description": "b",
                    "assigned_to": "shipwright",
                    "depends_on": [],
                    "artifacts": [],
                }
            ]
        }
        require_can_enter_tdd(_mock_voyage(), plan, [_mock_poneglyph(1)])

    def test_tdd_guard_accepts_alternate_roles(self) -> None:
        plan = MagicMock()
        plan.phases = {
            "phases": [
                _plan_phase_dict(1, "captain"),
                _plan_phase_dict(2, "shipwright"),
            ]
        }
        require_can_enter_tdd(_mock_voyage(), plan, [_mock_poneglyph(1), _mock_poneglyph(2)])


def _plan_phase_dict(n: int, assigned_to: str) -> dict[str, Any]:
    return {
        "phase_number": n,
        "name": f"phase {n}",
        "description": "x",
        "assigned_to": assigned_to,
        "depends_on": [],
        "artifacts": [],
    }
