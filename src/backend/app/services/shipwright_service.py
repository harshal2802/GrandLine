"""ShipwrightService — orchestrates phase-scoped code generation.

One invocation of `build_code` covers ONE phase and owns the iteration loop
(generate → run_tests → refine) up to `SHIPWRIGHT_MAX_ITERATIONS` attempts.
The LangGraph runs one iteration per `.ainvoke()`; the service writes a
per-iteration VivreCard so long loops don't lose progress.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crew.shipwright_graph import build_shipwright_graph
from app.den_den_mushi.constants import stream_key
from app.den_den_mushi.events import CodeGeneratedEvent, TestsPassedEvent
from app.den_den_mushi.mushi import DenDenMushi
from app.dial_system.router import DialSystemRouter
from app.models.build_artifact import BuildArtifact
from app.models.enums import CrewRole, VoyageStatus
from app.models.health_check import HealthCheck
from app.models.poneglyph import Poneglyph
from app.models.shipwright_run import ShipwrightRun
from app.models.vivre_card import VivreCard
from app.models.voyage import Voyage
from app.schemas.shipwright import BuildResultResponse
from app.services.execution_service import ExecutionService
from app.services.git_service import GitService

logger = logging.getLogger(__name__)

SHIPWRIGHT_MAX_ITERATIONS = 3
_OUTPUT_TRUNCATE = 4000


class ShipwrightError(Exception):
    """Raised when Shipwright agent operations fail at the service layer."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class ShipwrightService:
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
        self._graph = build_shipwright_graph(dial_router, execution_service)

    @classmethod
    def reader(cls, session: AsyncSession) -> ShipwrightService:
        """Create a read-only instance that only needs a DB session."""
        inst = cls.__new__(cls)
        inst._session = session
        inst._dial_router = None  # type: ignore[assignment]
        inst._mushi = None  # type: ignore[assignment]
        inst._execution = None  # type: ignore[assignment]
        inst._git = None
        inst._graph = None  # type: ignore[assignment]
        return inst

    async def build_code(
        self,
        voyage: Voyage,
        phase_number: int,
        poneglyph: Poneglyph,
        health_checks: list[HealthCheck],
        user_id: uuid.UUID,
    ) -> BuildResultResponse:
        non_pytest = [hc for hc in health_checks if hc.framework != "pytest"]
        if non_pytest:
            raise ShipwrightError(
                "VITEST_NOT_SUPPORTED",
                (
                    f"Only pytest health checks are supported in v1; found "
                    f"{sorted({hc.framework for hc in non_pytest})} — see "
                    "decisions.md 2026-04-17"
                ),
            )

        voyage.status = VoyageStatus.BUILDING.value
        await self._session.flush()

        state: dict[str, Any] = {
            "voyage_id": voyage.id,
            "user_id": user_id,
            "phase_number": phase_number,
            "poneglyph": {
                "phase_number": poneglyph.phase_number,
                **_parse_poneglyph_content(poneglyph),
            },
            "health_checks": [
                {
                    "file_path": hc.file_path,
                    "content": hc.content,
                    "framework": hc.framework,
                }
                for hc in health_checks
            ],
            "iteration": 1,
            "last_test_output": None,
            "raw_output": "",
            "generated_files": None,
            "exit_code": None,
            "stdout": "",
            "passed_count": 0,
            "failed_count": 0,
            "total_count": 0,
            "error": None,
        }

        iteration_count = 0
        final_parse_error: str | None = None
        try:
            for i in range(1, SHIPWRIGHT_MAX_ITERATIONS + 1):
                iteration_count = i
                state["iteration"] = i
                state = await self._graph.ainvoke(state)
                await self._checkpoint_iteration(voyage, state)

                if state.get("error"):
                    final_parse_error = state["error"]
                    if i < SHIPWRIGHT_MAX_ITERATIONS:
                        state["last_test_output"] = f"Previous JSON parse failed: {state['error']}"
                        continue
                    break

                final_parse_error = None
                if state.get("exit_code") == 0:
                    break

                state["last_test_output"] = state.get("stdout", "")
        except Exception:
            voyage.status = VoyageStatus.CHARTED.value
            await self._session.flush()
            raise

        passed = state.get("exit_code") == 0
        if passed:
            status_str: str = "passed"
        elif final_parse_error is not None:
            status_str = "failed"
        else:
            status_str = "max_iterations"
        generated_files = state.get("generated_files") or []
        stdout = state.get("stdout") or ""
        truncated = stdout[-_OUTPUT_TRUNCATE:] or (final_parse_error or "")

        run = ShipwrightRun(
            id=uuid.uuid4(),
            voyage_id=voyage.id,
            poneglyph_id=poneglyph.id,
            phase_number=phase_number,
            status=status_str,
            iteration_count=iteration_count,
            exit_code=state.get("exit_code"),
            passed_count=state.get("passed_count", 0),
            failed_count=state.get("failed_count", 0),
            total_count=state.get("total_count", 0),
            output=truncated,
        )
        self._session.add(run)
        await self._session.flush()

        artifacts: list[BuildArtifact] = []
        if passed:
            await self._session.execute(
                delete(BuildArtifact).where(
                    BuildArtifact.voyage_id == voyage.id,
                    BuildArtifact.phase_number == phase_number,
                )
            )
            for spec in generated_files:
                artifact = BuildArtifact(
                    voyage_id=voyage.id,
                    shipwright_run_id=run.id,
                    phase_number=phase_number,
                    file_path=spec.file_path,
                    content=spec.content,
                    language=spec.language,
                    created_by="shipwright",
                )
                self._session.add(artifact)
                artifacts.append(artifact)

        card = VivreCard(
            voyage_id=voyage.id,
            crew_member="shipwright",
            state_data={
                "phase_number": phase_number,
                "iteration_count": iteration_count,
                "status": status_str,
                "file_count": len(artifacts),
            },
            checkpoint_reason="build_complete",
        )
        self._session.add(card)

        voyage.status = VoyageStatus.CHARTED.value
        await self._session.commit()
        await self._session.refresh(run)
        for artifact in artifacts:
            await self._session.refresh(artifact)

        if passed:
            await self._maybe_commit_to_git(voyage, user_id, phase_number, artifacts)
            await self._publish_success_events(voyage.id, phase_number, run, artifacts)

        if final_parse_error is not None:
            raise ShipwrightError(
                "BUILD_PARSE_FAILED",
                (
                    f"Failed to parse LLM output after {iteration_count} iterations: "
                    f"{final_parse_error}"
                ),
            )

        return BuildResultResponse(
            voyage_id=voyage.id,
            phase_number=phase_number,
            shipwright_run_id=run.id,
            status=status_str,
            iteration_count=iteration_count,
            passed_count=run.passed_count,
            failed_count=run.failed_count,
            total_count=run.total_count,
            file_count=len(artifacts),
            summary=truncated[-500:],
        )

    async def _checkpoint_iteration(
        self,
        voyage: Voyage,
        state: dict[str, Any],
    ) -> None:
        """Best-effort per-iteration checkpoint. A failure logs and returns."""
        try:
            generated = state.get("generated_files") or []
            card = VivreCard(
                voyage_id=voyage.id,
                crew_member="shipwright",
                state_data={
                    "phase_number": state.get("phase_number"),
                    "iteration": state.get("iteration"),
                    "exit_code": state.get("exit_code"),
                    "file_count": len(generated),
                },
                checkpoint_reason="iteration",
            )
            self._session.add(card)
            await self._session.flush()
        except Exception:
            logger.warning(
                "Failed to checkpoint iteration %s for voyage %s",
                state.get("iteration"),
                voyage.id,
                exc_info=True,
            )

    async def _maybe_commit_to_git(
        self,
        voyage: Voyage,
        user_id: uuid.UUID,
        phase_number: int,
        artifacts: list[BuildArtifact],
    ) -> None:
        """Best-effort git commit of the Shipwright's source files."""
        if self._git is None or not voyage.target_repo or not artifacts:
            return
        try:
            await self._git.create_branch(voyage.id, user_id, "shipwright", "main")
            files = {a.file_path: a.content for a in artifacts}
            await self._git.commit(
                voyage.id,
                user_id,
                f"feat(phase-{phase_number}): Shipwright implementation",
                crew_member="shipwright",
                files=files,
            )
            branch = f"agent/shipwright/{voyage.id.hex[:8]}"
            await self._git.push(voyage.id, user_id, branch)
        except Exception:
            logger.warning(
                "Git commit failed for Shipwright phase %s on voyage %s",
                phase_number,
                voyage.id,
                exc_info=True,
            )

    async def _publish_success_events(
        self,
        voyage_id: uuid.UUID,
        phase_number: int,
        run: ShipwrightRun,
        artifacts: list[BuildArtifact],
    ) -> None:
        try:
            code_event = CodeGeneratedEvent(
                voyage_id=voyage_id,
                source_role=CrewRole.SHIPWRIGHT,
                payload={
                    "phase_number": phase_number,
                    "shipwright_run_id": str(run.id),
                    "file_count": len(artifacts),
                },
            )
            tests_event = TestsPassedEvent(
                voyage_id=voyage_id,
                source_role=CrewRole.SHIPWRIGHT,
                payload={
                    "phase_number": phase_number,
                    "shipwright_run_id": str(run.id),
                    "passed_count": run.passed_count,
                },
            )
            await self._mushi.publish(stream_key(voyage_id), code_event)
            await self._mushi.publish(stream_key(voyage_id), tests_event)
        except Exception:
            logger.warning(
                "Failed to publish Shipwright success events for voyage %s",
                voyage_id,
                exc_info=True,
            )

    async def get_build_artifacts(
        self,
        voyage_id: uuid.UUID,
        phase_number: int | None = None,
    ) -> list[BuildArtifact]:
        stmt = select(BuildArtifact).where(BuildArtifact.voyage_id == voyage_id)
        if phase_number is not None:
            stmt = stmt.where(BuildArtifact.phase_number == phase_number)
        stmt = stmt.order_by(BuildArtifact.phase_number, BuildArtifact.file_path)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_run(
        self,
        voyage_id: uuid.UUID,
        phase_number: int,
    ) -> ShipwrightRun | None:
        result = await self._session.execute(
            select(ShipwrightRun)
            .where(
                ShipwrightRun.voyage_id == voyage_id,
                ShipwrightRun.phase_number == phase_number,
            )
            .order_by(ShipwrightRun.created_at.desc())
            .limit(1)
        )
        return result.scalars().first()


def _parse_poneglyph_content(poneglyph: Poneglyph) -> dict[str, Any]:
    """Load the JSON content of a Poneglyph. On malformed JSON, warn and fall back."""
    try:
        data = json.loads(poneglyph.content)
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "Poneglyph %s (phase %s) has malformed content — using empty fallback",
            poneglyph.id,
            poneglyph.phase_number,
        )
        return {}
    return data if isinstance(data, dict) else {}
