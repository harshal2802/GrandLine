"""Tests for Shipwright Agent REST API endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.models.enums import VoyageStatus
from app.schemas.shipwright import BuildResultResponse
from app.services.shipwright_service import ShipwrightError

VOYAGE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
RUN_ID = uuid.uuid4()
ARTIFACT_ID_1 = uuid.uuid4()
ARTIFACT_ID_2 = uuid.uuid4()
PONEGLYPH_ID = uuid.uuid4()
HC_ID = uuid.uuid4()


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = USER_ID
    return user


def _mock_voyage(status: str = VoyageStatus.CHARTED.value) -> MagicMock:
    voyage = MagicMock()
    voyage.id = VOYAGE_ID
    voyage.user_id = USER_ID
    voyage.status = status
    return voyage


def _mock_poneglyph(phase_number: int = 1) -> MagicMock:
    p = MagicMock()
    p.id = PONEGLYPH_ID
    p.voyage_id = VOYAGE_ID
    p.phase_number = phase_number
    p.content = '{"title": "Phase 1"}'
    return p


def _mock_health_check(phase_number: int = 1) -> MagicMock:
    hc = MagicMock()
    hc.id = HC_ID
    hc.voyage_id = VOYAGE_ID
    hc.phase_number = phase_number
    hc.file_path = f"tests/test_phase{phase_number}.py"
    hc.content = "def test_x(): assert False"
    hc.framework = "pytest"
    return hc


def _mock_artifact(artifact_id: uuid.UUID, phase_number: int, file_path: str) -> MagicMock:
    a = MagicMock()
    a.id = artifact_id
    a.voyage_id = VOYAGE_ID
    a.shipwright_run_id = RUN_ID
    a.phase_number = phase_number
    a.file_path = file_path
    a.content = "def f(): pass"
    a.language = "python"
    a.created_by = "shipwright"
    a.created_at = datetime(2026, 4, 17, tzinfo=UTC)
    return a


def _mock_run(
    phase_number: int = 1, status_: str = "passed", iteration_count: int = 1
) -> MagicMock:
    r = MagicMock()
    r.id = RUN_ID
    r.voyage_id = VOYAGE_ID
    r.phase_number = phase_number
    r.status = status_
    r.iteration_count = iteration_count
    r.exit_code = 0 if status_ == "passed" else 1
    r.passed_count = 2
    r.failed_count = 0
    r.total_count = 2
    r.output = "2 passed"
    r.created_at = datetime(2026, 4, 17, tzinfo=UTC)
    return r


def _mock_shipwright_service(phase_number: int = 1) -> AsyncMock:
    svc = AsyncMock()
    svc.build_code = AsyncMock(
        return_value=BuildResultResponse(
            voyage_id=VOYAGE_ID,
            phase_number=phase_number,
            shipwright_run_id=RUN_ID,
            status="passed",
            iteration_count=1,
            passed_count=2,
            failed_count=0,
            total_count=2,
            file_count=2,
            summary="2 passed",
        )
    )
    svc.get_latest_run = AsyncMock(return_value=_mock_run(phase_number))
    svc.get_build_artifacts = AsyncMock(
        return_value=[
            _mock_artifact(ARTIFACT_ID_1, phase_number, "src/a.py"),
            _mock_artifact(ARTIFACT_ID_2, phase_number, "src/b.py"),
        ]
    )
    return svc


def _mock_navigator_reader(phase_number: int = 1) -> AsyncMock:
    nav = AsyncMock()
    nav.get_poneglyphs = AsyncMock(return_value=[_mock_poneglyph(phase_number)])
    return nav


def _mock_doctor_reader(phase_number: int = 1) -> AsyncMock:
    doc = AsyncMock()
    doc.get_health_checks = AsyncMock(return_value=[_mock_health_check(phase_number)])
    return doc


class TestBuildPhaseEndpoint:
    @pytest.mark.asyncio
    async def test_returns_201_with_build_result(self) -> None:
        from app.api.v1.shipwright import build_phase

        sw = _mock_shipwright_service()
        result = await build_phase(
            VOYAGE_ID,
            1,
            _mock_user(),
            _mock_voyage(),
            sw,
            _mock_navigator_reader(),
            _mock_doctor_reader(),
        )
        assert result.status == "passed"
        assert result.phase_number == 1
        sw.build_code.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_409_if_not_charted(self) -> None:
        from app.api.v1.shipwright import build_phase

        sw = _mock_shipwright_service()
        voyage = _mock_voyage(status=VoyageStatus.BUILDING.value)

        with pytest.raises(HTTPException) as exc_info:
            await build_phase(
                VOYAGE_ID,
                1,
                _mock_user(),
                voyage,
                sw,
                _mock_navigator_reader(),
                _mock_doctor_reader(),
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error"]["code"] == "VOYAGE_NOT_BUILDABLE"
        sw.build_code.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_404_when_poneglyph_missing(self) -> None:
        from app.api.v1.shipwright import build_phase

        sw = _mock_shipwright_service()
        nav = _mock_navigator_reader()
        nav.get_poneglyphs.return_value = []

        with pytest.raises(HTTPException) as exc_info:
            await build_phase(
                VOYAGE_ID,
                1,
                _mock_user(),
                _mock_voyage(),
                sw,
                nav,
                _mock_doctor_reader(),
            )
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["error"]["code"] == "PONEGLYPH_NOT_FOUND"
        sw.build_code.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_404_when_health_checks_missing(self) -> None:
        from app.api.v1.shipwright import build_phase

        sw = _mock_shipwright_service()
        doc = _mock_doctor_reader()
        doc.get_health_checks.return_value = []

        with pytest.raises(HTTPException) as exc_info:
            await build_phase(
                VOYAGE_ID,
                1,
                _mock_user(),
                _mock_voyage(),
                sw,
                _mock_navigator_reader(),
                doc,
            )
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["error"]["code"] == "HEALTH_CHECKS_NOT_FOUND"
        sw.build_code.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_422_on_shipwright_error(self) -> None:
        from app.api.v1.shipwright import build_phase

        sw = _mock_shipwright_service()
        sw.build_code.side_effect = ShipwrightError("BUILD_PARSE_FAILED", "LLM JSON parse failed")

        with pytest.raises(HTTPException) as exc_info:
            await build_phase(
                VOYAGE_ID,
                1,
                _mock_user(),
                _mock_voyage(),
                sw,
                _mock_navigator_reader(),
                _mock_doctor_reader(),
            )
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"]["code"] == "BUILD_PARSE_FAILED"

    @pytest.mark.asyncio
    async def test_returns_422_on_vitest_not_supported(self) -> None:
        from app.api.v1.shipwright import build_phase

        sw = _mock_shipwright_service()
        sw.build_code.side_effect = ShipwrightError("VITEST_NOT_SUPPORTED", "vitest deferred")

        with pytest.raises(HTTPException) as exc_info:
            await build_phase(
                VOYAGE_ID,
                1,
                _mock_user(),
                _mock_voyage(),
                sw,
                _mock_navigator_reader(),
                _mock_doctor_reader(),
            )
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"]["code"] == "VITEST_NOT_SUPPORTED"


class TestGetPhaseBuildEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_latest_run(self) -> None:
        from app.api.v1.shipwright import get_phase_build

        sw = _mock_shipwright_service()
        result = await get_phase_build(VOYAGE_ID, 1, _mock_user(), _mock_voyage(), sw)
        assert result.status == "passed"
        assert result.shipwright_run_id == RUN_ID
        assert result.file_count == 2

    @pytest.mark.asyncio
    async def test_returns_404_when_no_run(self) -> None:
        from app.api.v1.shipwright import get_phase_build

        sw = _mock_shipwright_service()
        sw.get_latest_run.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_phase_build(VOYAGE_ID, 1, _mock_user(), _mock_voyage(), sw)
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["error"]["code"] == "BUILD_NOT_FOUND"


class TestListBuildArtifactsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_list(self) -> None:
        from app.api.v1.shipwright import list_build_artifacts

        sw = _mock_shipwright_service()
        result = await list_build_artifacts(VOYAGE_ID, None, _mock_user(), _mock_voyage(), sw)
        assert len(result.artifacts) == 2
        assert result.phase_number is None

    @pytest.mark.asyncio
    async def test_filters_by_phase_number(self) -> None:
        from app.api.v1.shipwright import list_build_artifacts

        sw = _mock_shipwright_service()
        result = await list_build_artifacts(VOYAGE_ID, 2, _mock_user(), _mock_voyage(), sw)
        sw.get_build_artifacts.assert_awaited_once_with(VOYAGE_ID, 2)
        assert result.phase_number == 2

    @pytest.mark.asyncio
    async def test_returns_200_with_empty_list(self) -> None:
        from app.api.v1.shipwright import list_build_artifacts

        sw = _mock_shipwright_service()
        sw.get_build_artifacts.return_value = []

        result = await list_build_artifacts(VOYAGE_ID, None, _mock_user(), _mock_voyage(), sw)
        assert result.artifacts == []
