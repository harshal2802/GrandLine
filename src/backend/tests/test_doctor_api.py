"""Tests for Doctor Agent REST API endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.models.enums import VoyageStatus
from app.schemas.doctor import ValidateCodeRequest, ValidationResultResponse
from app.services.doctor_service import DoctorError

VOYAGE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
HC_ID_1 = uuid.uuid4()
HC_ID_2 = uuid.uuid4()
PONEGLYPH_ID_1 = uuid.uuid4()
PONEGLYPH_ID_2 = uuid.uuid4()


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


def _mock_poneglyph(poneglyph_id: uuid.UUID, phase_number: int) -> MagicMock:
    p = MagicMock()
    p.id = poneglyph_id
    p.voyage_id = VOYAGE_ID
    p.phase_number = phase_number
    p.content = '{"title": "Test"}'
    return p


def _mock_health_check(hc_id: uuid.UUID, phase_number: int) -> MagicMock:
    hc = MagicMock()
    hc.id = hc_id
    hc.voyage_id = VOYAGE_ID
    hc.poneglyph_id = PONEGLYPH_ID_1
    hc.phase_number = phase_number
    hc.file_path = f"tests/test_phase{phase_number}.py"
    hc.content = "def test_x(): assert False"
    hc.framework = "pytest"
    hc.last_run_status = None
    hc.last_run_output = None
    hc.last_run_at = None
    hc.metadata_ = {"framework": "pytest"}
    hc.created_by = "doctor"
    hc.created_at = datetime(2026, 4, 16, tzinfo=UTC)
    return hc


def _mock_doctor_service() -> AsyncMock:
    svc = AsyncMock()
    svc.write_health_checks = AsyncMock(
        return_value=[
            _mock_health_check(HC_ID_1, 1),
            _mock_health_check(HC_ID_2, 2),
        ]
    )
    svc.get_health_checks = AsyncMock(
        return_value=[
            _mock_health_check(HC_ID_1, 1),
            _mock_health_check(HC_ID_2, 2),
        ]
    )
    svc.validate_code = AsyncMock(
        return_value=ValidationResultResponse(
            voyage_id=VOYAGE_ID,
            status="passed",
            passed_count=2,
            failed_count=0,
            total_count=2,
            summary="2 passed",
        )
    )
    return svc


def _mock_navigator_reader() -> AsyncMock:
    svc = AsyncMock()
    svc.get_poneglyphs = AsyncMock(
        return_value=[
            _mock_poneglyph(PONEGLYPH_ID_1, 1),
            _mock_poneglyph(PONEGLYPH_ID_2, 2),
        ]
    )
    return svc


class TestWriteHealthChecksEndpoint:
    @pytest.mark.asyncio
    async def test_returns_201_with_health_check_ids(self) -> None:
        from app.api.v1.doctor import write_health_checks

        doc_svc = _mock_doctor_service()
        nav_reader = _mock_navigator_reader()

        result = await write_health_checks(
            VOYAGE_ID, _mock_user(), _mock_voyage(), doc_svc, nav_reader
        )

        assert result.voyage_id == VOYAGE_ID
        assert result.count == 2
        assert HC_ID_1 in result.health_check_ids
        doc_svc.write_health_checks.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_409_if_not_charted(self) -> None:
        from app.api.v1.doctor import write_health_checks

        doc_svc = _mock_doctor_service()
        nav_reader = _mock_navigator_reader()
        voyage = _mock_voyage(status=VoyageStatus.PLANNING.value)

        with pytest.raises(HTTPException) as exc_info:
            await write_health_checks(VOYAGE_ID, _mock_user(), voyage, doc_svc, nav_reader)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error"]["code"] == "VOYAGE_NOT_CHARTABLE"

    @pytest.mark.asyncio
    async def test_returns_404_if_no_poneglyphs(self) -> None:
        from app.api.v1.doctor import write_health_checks

        doc_svc = _mock_doctor_service()
        nav_reader = _mock_navigator_reader()
        nav_reader.get_poneglyphs.return_value = []

        with pytest.raises(HTTPException) as exc_info:
            await write_health_checks(VOYAGE_ID, _mock_user(), _mock_voyage(), doc_svc, nav_reader)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["error"]["code"] == "PONEGLYPHS_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_returns_422_on_doctor_error(self) -> None:
        from app.api.v1.doctor import write_health_checks

        doc_svc = _mock_doctor_service()
        doc_svc.write_health_checks.side_effect = DoctorError(
            "HEALTH_CHECK_PARSE_FAILED", "Bad LLM output"
        )
        nav_reader = _mock_navigator_reader()

        with pytest.raises(HTTPException) as exc_info:
            await write_health_checks(VOYAGE_ID, _mock_user(), _mock_voyage(), doc_svc, nav_reader)

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"]["code"] == "HEALTH_CHECK_PARSE_FAILED"


class TestGetHealthChecksEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_health_checks(self) -> None:
        from app.api.v1.doctor import get_health_checks

        doc_svc = _mock_doctor_service()

        result = await get_health_checks(VOYAGE_ID, _mock_user(), _mock_voyage(), doc_svc)

        assert result.voyage_id == VOYAGE_ID
        assert len(result.health_checks) == 2

    @pytest.mark.asyncio
    async def test_returns_200_with_empty_list(self) -> None:
        from app.api.v1.doctor import get_health_checks

        doc_svc = _mock_doctor_service()
        doc_svc.get_health_checks.return_value = []

        result = await get_health_checks(VOYAGE_ID, _mock_user(), _mock_voyage(), doc_svc)

        assert result.voyage_id == VOYAGE_ID
        assert result.health_checks == []


class TestRunValidationEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_passed_result(self) -> None:
        from app.api.v1.doctor import run_validation

        doc_svc = _mock_doctor_service()
        body = ValidateCodeRequest(files={"src/main.py": "print('hi')"})

        result = await run_validation(VOYAGE_ID, body, _mock_user(), _mock_voyage(), doc_svc)

        assert result.status == "passed"
        assert result.passed_count == 2
        doc_svc.validate_code.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_200_with_failed_result(self) -> None:
        from app.api.v1.doctor import run_validation

        doc_svc = _mock_doctor_service()
        doc_svc.validate_code.return_value = ValidationResultResponse(
            voyage_id=VOYAGE_ID,
            status="failed",
            passed_count=1,
            failed_count=1,
            total_count=2,
            summary="1 failed",
        )
        body = ValidateCodeRequest(files={"src/main.py": "print('hi')"})

        result = await run_validation(VOYAGE_ID, body, _mock_user(), _mock_voyage(), doc_svc)

        assert result.status == "failed"
        assert result.failed_count == 1

    @pytest.mark.asyncio
    async def test_returns_409_if_not_charted(self) -> None:
        from app.api.v1.doctor import run_validation

        doc_svc = _mock_doctor_service()
        body = ValidateCodeRequest(files={"src/main.py": "print('hi')"})
        voyage = _mock_voyage(status=VoyageStatus.PLANNING.value)

        with pytest.raises(HTTPException) as exc_info:
            await run_validation(VOYAGE_ID, body, _mock_user(), voyage, doc_svc)

        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_returns_422_on_no_health_checks(self) -> None:
        from app.api.v1.doctor import run_validation

        doc_svc = _mock_doctor_service()
        doc_svc.validate_code.side_effect = DoctorError("NO_HEALTH_CHECKS", "No health checks")
        body = ValidateCodeRequest(files={"src/main.py": "print('hi')"})

        with pytest.raises(HTTPException) as exc_info:
            await run_validation(VOYAGE_ID, body, _mock_user(), _mock_voyage(), doc_svc)

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"]["code"] == "NO_HEALTH_CHECKS"
