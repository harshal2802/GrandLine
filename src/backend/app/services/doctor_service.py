"""DoctorService — orchestrates health-check generation and code validation."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crew.doctor_graph import build_doctor_graph
from app.den_den_mushi.constants import stream_key
from app.den_den_mushi.events import (
    HealthCheckWrittenEvent,
    ValidationFailedEvent,
    ValidationPassedEvent,
)
from app.den_den_mushi.mushi import DenDenMushi
from app.dial_system.router import DialSystemRouter
from app.models.enums import CrewRole, VoyageStatus
from app.models.health_check import HealthCheck
from app.models.poneglyph import Poneglyph
from app.models.validation_run import ValidationRun
from app.models.vivre_card import VivreCard
from app.models.voyage import Voyage
from app.schemas.doctor import HealthCheckSpec, ValidationResultResponse
from app.schemas.execution import ExecutionRequest
from app.services.execution_service import ExecutionService
from app.services.git_service import GitService

logger = logging.getLogger(__name__)

_PYTEST_SUMMARY_RE = re.compile(
    r"(?P<passed>\d+)\s+passed|(?P<failed>\d+)\s+failed",
    re.IGNORECASE,
)
_OUTPUT_TRUNCATE = 4000


class DoctorError(Exception):
    """Raised when Doctor agent operations fail."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class DoctorService:
    def __init__(
        self,
        dial_router: DialSystemRouter,
        mushi: DenDenMushi,
        session: AsyncSession,
        execution_service: ExecutionService,
        git_service: GitService | None = None,
    ) -> None:
        self._dial_router = dial_router
        self._mushi = mushi
        self._session = session
        self._execution = execution_service
        self._git = git_service
        self._graph = build_doctor_graph(dial_router)

    @classmethod
    def reader(cls, session: AsyncSession) -> DoctorService:
        """Create a read-only instance that only needs a DB session."""
        inst = cls.__new__(cls)
        inst._session = session
        inst._dial_router = None  # type: ignore[assignment]
        inst._mushi = None  # type: ignore[assignment]
        inst._execution = None  # type: ignore[assignment]
        inst._git = None
        inst._graph = None  # type: ignore[assignment]
        return inst

    async def write_health_checks(
        self,
        voyage: Voyage,
        poneglyphs: list[Poneglyph],
        user_id: uuid.UUID,
    ) -> list[HealthCheck]:
        voyage.status = VoyageStatus.TDD.value
        await self._session.flush()

        graph_input = _poneglyphs_to_graph_input(poneglyphs)

        try:
            result = await self._graph.ainvoke(
                {
                    "poneglyphs": graph_input,
                    "raw_output": "",
                    "health_checks": None,
                    "error": None,
                }
            )
        except Exception:
            voyage.status = VoyageStatus.CHARTED.value
            await self._session.flush()
            raise

        specs: list[HealthCheckSpec] | None = result.get("health_checks")
        if specs is None:
            voyage.status = VoyageStatus.CHARTED.value
            await self._session.flush()
            error = result.get("error", "Unknown error")
            raise DoctorError(
                "HEALTH_CHECK_PARSE_FAILED",
                f"Failed to parse health checks: {error}",
            )

        poneglyph_phase_numbers = {p.phase_number for p in poneglyphs}
        spec_phase_numbers = {s.phase_number for s in specs}
        if not spec_phase_numbers.issubset(poneglyph_phase_numbers):
            voyage.status = VoyageStatus.CHARTED.value
            await self._session.flush()
            raise DoctorError(
                "HEALTH_CHECK_PHASE_MISMATCH",
                (
                    f"Health-check phases {sorted(spec_phase_numbers)} are not a subset"
                    f" of Poneglyph phases {sorted(poneglyph_phase_numbers)}"
                ),
            )

        await self._session.execute(delete(HealthCheck).where(HealthCheck.voyage_id == voyage.id))

        poneglyph_by_phase: dict[int, Poneglyph] = {p.phase_number: p for p in poneglyphs}
        health_checks: list[HealthCheck] = []
        for spec in specs:
            linked = poneglyph_by_phase.get(spec.phase_number)
            hc = HealthCheck(
                voyage_id=voyage.id,
                poneglyph_id=linked.id if linked else None,
                phase_number=spec.phase_number,
                file_path=spec.file_path,
                content=spec.content,
                framework=spec.framework,
                created_by="doctor",
            )
            self._session.add(hc)
            health_checks.append(hc)

        card = VivreCard(
            voyage_id=voyage.id,
            crew_member="doctor",
            state_data={
                "health_check_count": len(health_checks),
                "phase_numbers": [s.phase_number for s in specs],
            },
            checkpoint_reason="health_checks_written",
        )
        self._session.add(card)

        voyage.status = VoyageStatus.CHARTED.value

        await self._session.commit()
        for hc in health_checks:
            await self._session.refresh(hc)

        await self._maybe_commit_to_git(voyage, user_id, health_checks)

        try:
            for hc in health_checks:
                event = HealthCheckWrittenEvent(
                    voyage_id=voyage.id,
                    source_role=CrewRole.DOCTOR,
                    payload={
                        "health_check_id": str(hc.id),
                        "phase_number": hc.phase_number,
                        "file_path": hc.file_path,
                    },
                )
                await self._mushi.publish(stream_key(voyage.id), event)
        except Exception:
            logger.warning(
                "Failed to publish health_check_written events for voyage %s",
                voyage.id,
                exc_info=True,
            )

        return health_checks

    async def _maybe_commit_to_git(
        self,
        voyage: Voyage,
        user_id: uuid.UUID,
        health_checks: list[HealthCheck],
    ) -> None:
        """Best-effort: push the health checks to the Doctor's git branch."""
        if self._git is None or not voyage.target_repo:
            return
        try:
            await self._git.create_branch(voyage.id, user_id, "doctor", "main")
            files = {hc.file_path: hc.content for hc in health_checks}
            await self._git.commit(
                voyage.id,
                user_id,
                "test: add Doctor health checks",
                crew_member="doctor",
                files=files,
            )
            branch = f"agent/doctor/{voyage.id.hex[:8]}"
            await self._git.push(voyage.id, user_id, branch)
        except Exception:
            logger.warning(
                "Git commit failed for Doctor health checks on voyage %s",
                voyage.id,
                exc_info=True,
            )

    async def validate_code(
        self,
        voyage: Voyage,
        user_id: uuid.UUID,
        shipwright_files: dict[str, str],
    ) -> ValidationResultResponse:
        voyage.status = VoyageStatus.REVIEWING.value
        await self._session.flush()

        result = await self._session.execute(
            select(HealthCheck)
            .where(HealthCheck.voyage_id == voyage.id)
            .order_by(HealthCheck.phase_number)
        )
        health_checks = list(result.scalars().all())

        if not health_checks:
            voyage.status = VoyageStatus.CHARTED.value
            await self._session.flush()
            raise DoctorError(
                "NO_HEALTH_CHECKS",
                "No health checks found for voyage — run Doctor (write) first",
            )

        layered_files = dict(shipwright_files)
        for hc in health_checks:
            layered_files[hc.file_path] = hc.content

        exec_request = ExecutionRequest(
            command="cd /workspace && python -m pytest -x --tb=short",
            files=layered_files,
            timeout_seconds=300,
        )
        exec_result = await self._execution.run(user_id, exec_request)

        passed = exec_result.exit_code == 0
        status_str = "passed" if passed else "failed"
        passed_count, failed_count = _parse_counts(
            exec_result.stdout, passed=passed, total=len(health_checks)
        )
        truncated = (exec_result.stdout or "")[-_OUTPUT_TRUNCATE:]

        run = ValidationRun(
            voyage_id=voyage.id,
            status=status_str,
            exit_code=exec_result.exit_code,
            passed_count=passed_count,
            failed_count=failed_count,
            total_count=len(health_checks),
            output=truncated,
        )
        self._session.add(run)
        await self._session.flush()

        now = datetime.now(UTC)
        for hc in health_checks:
            hc.last_run_status = status_str
            hc.last_run_at = now
            hc.last_validation_run_id = run.id

        voyage.status = VoyageStatus.CHARTED.value
        await self._session.commit()

        response = ValidationResultResponse(
            voyage_id=voyage.id,
            status=status_str,
            passed_count=passed_count,
            failed_count=failed_count,
            total_count=len(health_checks),
            summary=truncated[-500:],
        )

        try:
            payload = {
                "passed_count": passed_count,
                "failed_count": failed_count,
                "total_count": len(health_checks),
            }
            event: ValidationPassedEvent | ValidationFailedEvent
            if passed:
                event = ValidationPassedEvent(
                    voyage_id=voyage.id,
                    source_role=CrewRole.DOCTOR,
                    payload=payload,
                )
            else:
                event = ValidationFailedEvent(
                    voyage_id=voyage.id,
                    source_role=CrewRole.DOCTOR,
                    payload=payload,
                )
            await self._mushi.publish(stream_key(voyage.id), event)
        except Exception:
            logger.warning(
                "Failed to publish validation event for voyage %s",
                voyage.id,
                exc_info=True,
            )

        return response

    async def get_health_checks(
        self,
        voyage_id: uuid.UUID,
    ) -> list[HealthCheck]:
        result = await self._session.execute(
            select(HealthCheck)
            .where(HealthCheck.voyage_id == voyage_id)
            .order_by(HealthCheck.phase_number)
        )
        return list(result.scalars().all())


def _poneglyphs_to_graph_input(poneglyphs: list[Poneglyph]) -> list[dict[str, Any]]:
    """Flatten each Poneglyph's persisted content for the graph input."""
    out: list[dict[str, Any]] = []
    for p in poneglyphs:
        try:
            content = json.loads(p.content)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Poneglyph %s (phase %s) has malformed content — using empty fallback",
                p.id,
                p.phase_number,
            )
            content = {}
        out.append(
            {
                "phase_number": p.phase_number,
                "title": content.get("title"),
                "task_description": content.get("task_description"),
                "test_criteria": content.get("test_criteria", []),
                "file_paths": content.get("file_paths", []),
            }
        )
    return out


def _parse_counts(stdout: str, passed: bool, total: int) -> tuple[int, int]:
    """Best-effort parse pytest summary for passed/failed counts."""
    passed_count = 0
    failed_count = 0
    for match in _PYTEST_SUMMARY_RE.finditer(stdout or ""):
        if match.group("passed"):
            passed_count += int(match.group("passed"))
        elif match.group("failed"):
            failed_count += int(match.group("failed"))
    if passed_count == 0 and failed_count == 0:
        if passed:
            passed_count = total
        else:
            failed_count = total
    return passed_count, failed_count
