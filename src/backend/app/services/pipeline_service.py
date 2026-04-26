"""PipelineService — orchestrates the full Voyage Pipeline via the master graph.

Composes the five crew services into a single end-to-end run. Adds
pipeline-level events and VivreCard checkpoints; delegates the per-stage DB
writes + per-service events + per-service checkpoints to the crew services
themselves (they already own that).

`start()` runs the graph synchronously to completion in the caller's event
loop. Phase 15.4 adds the `asyncio.create_task` wrapping at the API layer.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.crew.pipeline_graph import (
    PipelineContext,
    PipelineState,
    build_pipeline_graph,
)
from app.den_den_mushi.constants import stream_key
from app.den_den_mushi.events import (
    PipelineFailedEvent,
    PipelineStartedEvent,
)
from app.den_den_mushi.mushi import DenDenMushi
from app.deployment.backend import DeploymentBackend
from app.dial_system.router import DialSystemRouter
from app.models.build_artifact import BuildArtifact
from app.models.deployment import Deployment
from app.models.dial_config import DialConfig
from app.models.enums import CrewRole, VoyageStatus
from app.models.health_check import HealthCheck
from app.models.poneglyph import Poneglyph
from app.models.validation_run import ValidationRun
from app.models.vivre_card import VivreCard
from app.models.voyage import Voyage, VoyagePlan
from app.schemas.dial_config import resolve_shipwright_max_concurrency
from app.schemas.pipeline import PipelineStatusSnapshot
from app.services.execution_service import ExecutionService
from app.services.git_service import GitService
from app.services.pipeline_guards import (
    PipelineError,
    require_can_enter_planning,
)

logger = logging.getLogger(__name__)

_MAX_CONCURRENCY_FLOOR = 1
_MAX_CONCURRENCY_CEIL = 10
_TERMINAL_STATUSES = frozenset(
    {VoyageStatus.COMPLETED.value, VoyageStatus.FAILED.value, VoyageStatus.CANCELLED.value}
)
_RESUMABLE_STATUSES = frozenset({VoyageStatus.PAUSED.value, VoyageStatus.FAILED.value})
_NON_RESUMABLE_TERMINAL = frozenset({VoyageStatus.COMPLETED.value, VoyageStatus.CANCELLED.value})


class PipelineService:
    def __init__(
        self,
        session: AsyncSession,
        mushi: DenDenMushi,
        dial_router: DialSystemRouter,
        execution_service: ExecutionService,
        git_service: GitService | None,
        deployment_backend: DeploymentBackend,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session = session
        self._mushi = mushi
        self._dial_router = dial_router
        self._execution = execution_service
        self._git = git_service
        self._backend = deployment_backend
        self._session_factory = session_factory

    @classmethod
    def reader(cls, session: AsyncSession) -> PipelineService:
        inst = cls.__new__(cls)
        inst._session = session
        inst._mushi = None  # type: ignore[assignment]
        inst._dial_router = None  # type: ignore[assignment]
        inst._execution = None  # type: ignore[assignment]
        inst._git = None
        inst._backend = None  # type: ignore[assignment]
        inst._session_factory = None
        return inst

    async def start(
        self,
        voyage: Voyage,
        user_id: uuid.UUID,
        task: str,
        deploy_tier: Literal["preview"] = "preview",
        max_parallel_shipwrights: int | None = None,
    ) -> None:
        try:
            require_can_enter_planning(voyage)
        except PipelineError as exc:
            await self._publish_failed(voyage.id, exc.code, exc.message, "PLANNING")
            raise

        try:
            resolved_concurrency = await self._resolve_concurrency(
                voyage.id, max_parallel_shipwrights
            )
        except PipelineError as exc:
            await self._publish_failed(voyage.id, exc.code, exc.message, "PLANNING")
            raise

        run_start = time.monotonic()

        await self._publish(
            voyage.id,
            PipelineStartedEvent(
                voyage_id=voyage.id,
                source_role=CrewRole.CAPTAIN,
                payload={
                    "task": task,
                    "deploy_tier": deploy_tier,
                    "max_parallel_shipwrights": resolved_concurrency,
                },
            ),
        )

        ctx = PipelineContext(
            session=self._session,
            mushi=self._mushi,
            dial_router=self._dial_router,
            execution_service=self._execution,
            git_service=self._git,
            deployment_backend=self._backend,
            session_factory=self._session_factory,
        )
        graph = build_pipeline_graph(ctx)

        initial_state: PipelineState = {
            "voyage_id": voyage.id,
            "user_id": user_id,
            "deploy_tier": deploy_tier,
            "max_parallel_shipwrights": resolved_concurrency,
            "task": task,
            "start_monotonic": run_start,
            "plan_id": None,
            "poneglyph_count": 0,
            "health_check_count": 0,
            "build_artifact_count": 0,
            "validation_run_id": None,
            "deployment_id": None,
            "error": None,
            "paused": False,
        }

        try:
            final_state: PipelineState = await graph.ainvoke(initial_state)  # type: ignore[assignment]
        except Exception as exc:
            await self._mark_failed(voyage.id, "PIPELINE_INTERNAL", str(exc), "UNKNOWN")
            raise PipelineError("PIPELINE_INTERNAL", str(exc)) from exc

        if final_state.get("error"):
            err = final_state["error"] or {}
            raise PipelineError(
                err.get("code", "UNKNOWN"),
                err.get("message", "Pipeline failed"),
            )

        if final_state.get("paused"):
            return

        duration = time.monotonic() - run_start
        logger.info("Pipeline completed for voyage %s in %.2fs", voyage.id, duration)

    async def pause(self, voyage: Voyage) -> None:
        if voyage.status in _TERMINAL_STATUSES:
            return
        voyage.status = VoyageStatus.PAUSED.value
        self._session.add(voyage)
        await self._session.commit()

    async def resume(self, voyage: Voyage) -> None:
        """Flip a PAUSED or FAILED voyage back to CHARTED.

        - PAUSED / FAILED -> flip to CHARTED, commit.
        - CHARTED -> no-op (already runnable).
        - COMPLETED / CANCELLED -> raises VOYAGE_NOT_RESUMABLE.
        - Any active mid-pipeline status (PLANNING, PDD, TDD, BUILDING,
          REVIEWING, DEPLOYING) -> raises VOYAGE_NOT_RESUMABLE.

        After this returns, the caller spawns the pipeline graph; the graph's
        skip-already-satisfied logic picks up from the next unsatisfied stage.
        """
        if voyage.status == VoyageStatus.CHARTED.value:
            return
        if voyage.status in _NON_RESUMABLE_TERMINAL:
            raise PipelineError(
                "VOYAGE_NOT_RESUMABLE",
                f"Voyage status is {voyage.status}; cannot resume a "
                f"{voyage.status.lower()} voyage",
            )
        if voyage.status not in _RESUMABLE_STATUSES:
            raise PipelineError(
                "VOYAGE_NOT_RESUMABLE",
                f"Voyage status is {voyage.status}; cancel and restart, "
                f"or wait for the current run to reach a resumable state",
            )
        voyage.status = VoyageStatus.CHARTED.value
        self._session.add(voyage)
        await self._session.commit()

    async def cancel(self, voyage: Voyage) -> None:
        if voyage.status in _TERMINAL_STATUSES:
            return
        voyage.status = VoyageStatus.CANCELLED.value
        self._session.add(voyage)
        await self._session.commit()

    async def get_status(self, voyage: Voyage) -> PipelineStatusSnapshot:
        plan_exists_row = await self._session.execute(
            select(func.count()).select_from(VoyagePlan).where(VoyagePlan.voyage_id == voyage.id)
        )
        plan_exists = (plan_exists_row.scalar() or 0) > 0

        poneglyph_count = (
            await self._session.execute(
                select(func.count()).select_from(Poneglyph).where(Poneglyph.voyage_id == voyage.id)
            )
        ).scalar() or 0

        health_check_count = (
            await self._session.execute(
                select(func.count())
                .select_from(HealthCheck)
                .where(HealthCheck.voyage_id == voyage.id)
            )
        ).scalar() or 0

        build_artifact_count = (
            await self._session.execute(
                select(func.count())
                .select_from(BuildArtifact)
                .where(BuildArtifact.voyage_id == voyage.id)
            )
        ).scalar() or 0

        latest_val_row = await self._session.execute(
            select(ValidationRun)
            .where(ValidationRun.voyage_id == voyage.id)
            .order_by(ValidationRun.created_at.desc())
            .limit(1)
        )
        latest_val = latest_val_row.scalar_one_or_none()

        latest_dep_row = await self._session.execute(
            select(Deployment)
            .where(Deployment.voyage_id == voyage.id)
            .order_by(Deployment.created_at.desc())
            .limit(1)
        )
        latest_dep = latest_dep_row.scalar_one_or_none()

        error_card_row = await self._session.execute(
            select(VivreCard)
            .where(
                VivreCard.voyage_id == voyage.id,
                VivreCard.checkpoint_reason == "pipeline_failed",
            )
            .order_by(VivreCard.created_at.desc())
            .limit(1)
        )
        error_card = error_card_row.scalar_one_or_none()
        error: dict[str, Any] | None = None
        if error_card is not None:
            error = dict(error_card.state_data)

        return PipelineStatusSnapshot(
            voyage_id=voyage.id,
            status=voyage.status,
            plan_exists=plan_exists,
            poneglyph_count=int(poneglyph_count),
            health_check_count=int(health_check_count),
            build_artifact_count=int(build_artifact_count),
            phase_status={str(k): str(v) for k, v in (voyage.phase_status or {}).items()},
            last_validation_status=latest_val.status if latest_val else None,
            last_deployment_status=latest_dep.status if latest_dep else None,
            error=error,
        )

    async def _resolve_concurrency(self, voyage_id: uuid.UUID, override: int | None) -> int:
        if override is not None:
            if override < _MAX_CONCURRENCY_FLOOR or override > _MAX_CONCURRENCY_CEIL:
                raise PipelineError(
                    "INVALID_CONCURRENCY",
                    f"max_parallel_shipwrights must be between "
                    f"{_MAX_CONCURRENCY_FLOOR} and {_MAX_CONCURRENCY_CEIL}",
                )
            return override

        result = await self._session.execute(
            select(DialConfig).where(DialConfig.voyage_id == voyage_id).limit(1)
        )
        dial_config = result.scalar_one_or_none()
        role_mapping: dict[str, Any] | None = (
            dial_config.role_mapping if dial_config is not None else None
        )
        return resolve_shipwright_max_concurrency(role_mapping)

    async def _publish(self, voyage_id: uuid.UUID, event: Any) -> None:
        try:
            await self._mushi.publish(stream_key(voyage_id), event)
        except Exception:
            logger.warning(
                "Failed to publish %s for voyage %s",
                event.event_type,
                voyage_id,
                exc_info=True,
            )

    async def _publish_failed(
        self, voyage_id: uuid.UUID, code: str, message: str, stage: str
    ) -> None:
        await self._publish(
            voyage_id,
            PipelineFailedEvent(
                voyage_id=voyage_id,
                source_role=CrewRole.CAPTAIN,
                payload={"stage": stage, "code": code, "message": message},
            ),
        )

    async def _mark_failed(self, voyage_id: uuid.UUID, code: str, message: str, stage: str) -> None:
        result = await self._session.execute(select(Voyage).where(Voyage.id == voyage_id))
        voyage = result.scalar_one_or_none()
        if voyage is None:
            return
        voyage.status = VoyageStatus.FAILED.value
        self._session.add(voyage)
        try:
            await self._session.commit()
        except Exception:
            logger.warning("Failed to mark voyage %s as FAILED", voyage_id, exc_info=True)
        await self._publish(
            voyage_id,
            PipelineFailedEvent(
                voyage_id=voyage_id,
                source_role=CrewRole.CAPTAIN,
                payload={"stage": stage, "code": code, "message": message},
            ),
        )


__all__ = ["PipelineService"]
