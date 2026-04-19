"""HelmsmanService — orchestrates voyage deployments via a swappable
DeploymentBackend. One invocation covers one (voyage, tier) action.

Unlike Shipwright, Helmsman is mostly imperative. Its LangGraph is a thin
orchestrator that makes a single backend call and (on failure only) a single
LLM diagnosis call. The service owns DB writes, voyage status transitions,
VivreCard checkpoints, and best-effort event publishing.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crew.helmsman_graph import build_helmsman_graph
from app.den_den_mushi.constants import stream_key
from app.den_den_mushi.events import (
    DeploymentCompletedEvent,
    DeploymentFailedEvent,
    DeploymentStartedEvent,
)
from app.den_den_mushi.mushi import DenDenMushi
from app.deployment.backend import DeploymentBackend
from app.dial_system.router import DialSystemRouter
from app.models.deployment import Deployment
from app.models.enums import CrewRole, VoyageStatus
from app.models.vivre_card import VivreCard
from app.models.voyage import Voyage
from app.schemas.deployment import (
    DeploymentResponse,
    DeploymentTier,
)
from app.services.git_service import GitError, GitService

logger = logging.getLogger(__name__)

TRUNCATE = 4000

DEFAULT_GIT_REF_BY_TIER: dict[str, Callable[[uuid.UUID], str]] = {
    "preview": lambda voyage_id: f"agent/shipwright/{voyage_id.hex[:8]}",
    "staging": lambda _voyage_id: "staging",
    "production": lambda _voyage_id: "main",
}


class HelmsmanError(Exception):
    """Raised when Helmsman agent operations fail at the service layer."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _require_production_approval(
    tier: DeploymentTier,
    approved_by: uuid.UUID | None,
) -> None:
    """Phase 17 swap-point: replace this function to change approval semantics."""
    if tier == "production" and approved_by is None:
        raise HelmsmanError(
            "APPROVAL_REQUIRED",
            "Production deploys require approved_by to be set",
        )


class HelmsmanService:
    def __init__(
        self,
        dial_router: DialSystemRouter,
        mushi: DenDenMushi,
        session: AsyncSession,
        deployment_backend: DeploymentBackend,
        git_service: GitService | None = None,
    ) -> None:
        self._dial_router = dial_router
        self._mushi = mushi
        self._session = session
        self._backend = deployment_backend
        self._git = git_service
        self._graph = build_helmsman_graph(dial_router, deployment_backend)

    @classmethod
    def reader(cls, session: AsyncSession) -> HelmsmanService:
        """Create a read-only instance that only needs a DB session."""
        inst = cls.__new__(cls)
        inst._session = session
        inst._dial_router = None  # type: ignore[assignment]
        inst._mushi = None  # type: ignore[assignment]
        inst._backend = None  # type: ignore[assignment]
        inst._git = None
        inst._graph = None  # type: ignore[assignment]
        return inst

    async def deploy(
        self,
        voyage: Voyage,
        tier: DeploymentTier,
        user_id: uuid.UUID,
        git_ref: str | None = None,
        approved_by: uuid.UUID | None = None,
    ) -> DeploymentResponse:
        # Approval is checked BEFORE the status gate. An unapproved production
        # request against a non-CHARTED voyage returns 403, not 409.
        _require_production_approval(tier, approved_by)

        if voyage.status != VoyageStatus.CHARTED.value:
            raise HelmsmanError(
                "VOYAGE_NOT_DEPLOYABLE",
                f"Voyage status is {voyage.status}, expected CHARTED",
            )

        resolved_ref = git_ref or DEFAULT_GIT_REF_BY_TIER[tier](voyage.id)
        resolved_sha = await self._resolve_git_sha(voyage, user_id, resolved_ref)

        return await self._run_deployment(
            voyage=voyage,
            tier=tier,
            action="deploy",
            git_ref=resolved_ref,
            git_sha=resolved_sha,
            user_id=user_id,
            approved_by=approved_by,
            previous_deployment_id=None,
        )

    async def rollback(
        self,
        voyage: Voyage,
        tier: DeploymentTier,
        user_id: uuid.UUID,
    ) -> DeploymentResponse:
        if voyage.status != VoyageStatus.CHARTED.value:
            raise HelmsmanError(
                "VOYAGE_NOT_DEPLOYABLE",
                f"Voyage status is {voyage.status}, expected CHARTED",
            )

        previous = await self._find_previous_deployment(voyage.id, tier)
        if previous is None:
            raise HelmsmanError(
                "NO_PREVIOUS_DEPLOYMENT",
                f"No completed deploy found for voyage {voyage.id} tier {tier}",
            )

        return await self._run_deployment(
            voyage=voyage,
            tier=tier,
            action="rollback",
            git_ref=previous.git_ref,
            git_sha=previous.git_sha,
            user_id=user_id,
            approved_by=None,
            previous_deployment_id=previous.id,
        )

    async def _resolve_git_sha(
        self,
        voyage: Voyage,
        user_id: uuid.UUID,
        ref: str,
    ) -> str | None:
        if self._git is None or not voyage.target_repo:
            return None
        try:
            return await self._git.get_head_sha(voyage.id, user_id, ref)
        except GitError as exc:
            raise HelmsmanError(
                "GIT_REF_UNRESOLVABLE",
                f"Could not resolve git_ref {ref!r}: {exc}",
            ) from exc

    async def _find_previous_deployment(
        self,
        voyage_id: uuid.UUID,
        tier: DeploymentTier,
    ) -> Deployment | None:
        stmt = (
            select(Deployment)
            .where(
                Deployment.voyage_id == voyage_id,
                Deployment.tier == tier,
                Deployment.status == "completed",
                Deployment.action == "deploy",
            )
            .order_by(Deployment.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def _run_deployment(
        self,
        *,
        voyage: Voyage,
        tier: DeploymentTier,
        action: str,
        git_ref: str,
        git_sha: str | None,
        user_id: uuid.UUID,
        approved_by: uuid.UUID | None,
        previous_deployment_id: uuid.UUID | None,
    ) -> DeploymentResponse:
        voyage.status = VoyageStatus.DEPLOYING.value
        await self._session.flush()

        deployment = Deployment(
            id=uuid.uuid4(),
            voyage_id=voyage.id,
            tier=tier,
            action=action,
            git_ref=git_ref,
            git_sha=git_sha,
            status="running",
            approved_by=approved_by,
            previous_deployment_id=previous_deployment_id,
        )
        self._session.add(deployment)

        try:
            await self._session.flush()

            state: dict[str, Any] = {
                "voyage_id": voyage.id,
                "user_id": user_id,
                "tier": tier,
                "git_ref": git_ref,
                "git_sha": git_sha,
                "status": "failed",
                "url": None,
                "backend_log": "",
                "error": None,
                "diagnosis": None,
            }
            final_state = await self._graph.ainvoke(state)
        except Exception:
            voyage.status = VoyageStatus.CHARTED.value
            await self._session.flush()
            raise

        deployment.status = final_state["status"]
        deployment.url = final_state.get("url")
        deployment.backend_log = (final_state.get("backend_log") or "")[-TRUNCATE:]
        deployment.diagnosis = final_state.get("diagnosis")

        card = VivreCard(
            voyage_id=voyage.id,
            crew_member="helmsman",
            state_data={
                "tier": tier,
                "action": action,
                "status": deployment.status,
                "deployment_id": str(deployment.id),
                "git_sha": git_sha,
            },
            checkpoint_reason="deployment",
        )
        self._session.add(card)

        voyage.status = VoyageStatus.CHARTED.value
        await self._session.commit()
        await self._session.refresh(deployment)

        await self._publish_events(voyage.id, deployment)

        if deployment.status == "failed":
            summary = "Deployment failed"
            if deployment.diagnosis and deployment.diagnosis.get("summary"):
                summary = str(deployment.diagnosis["summary"])
            raise HelmsmanError("DEPLOYMENT_FAILED", summary)

        return DeploymentResponse(
            voyage_id=voyage.id,
            deployment_id=deployment.id,
            tier=tier,
            action=action,
            status=deployment.status,
            git_ref=deployment.git_ref,
            git_sha=deployment.git_sha,
            url=deployment.url,
            diagnosis=deployment.diagnosis,
        )

    async def _publish_events(
        self,
        voyage_id: uuid.UUID,
        deployment: Deployment,
    ) -> None:
        """Best-effort event publish. Each event publishes in its own try/except
        so one failure does not block the others."""
        base_payload = {
            "tier": deployment.tier,
            "action": deployment.action,
            "deployment_id": str(deployment.id),
            "git_ref": deployment.git_ref,
            "git_sha": deployment.git_sha,
        }
        started = DeploymentStartedEvent(
            voyage_id=voyage_id,
            source_role=CrewRole.HELMSMAN,
            payload=base_payload,
        )
        try:
            await self._mushi.publish(stream_key(voyage_id), started)
        except Exception:
            logger.warning(
                "Failed to publish DeploymentStartedEvent for voyage %s",
                voyage_id,
                exc_info=True,
            )

        if deployment.status == "completed":
            completed = DeploymentCompletedEvent(
                voyage_id=voyage_id,
                source_role=CrewRole.HELMSMAN,
                payload={**base_payload, "url": deployment.url},
            )
            try:
                await self._mushi.publish(stream_key(voyage_id), completed)
            except Exception:
                logger.warning(
                    "Failed to publish DeploymentCompletedEvent for voyage %s",
                    voyage_id,
                    exc_info=True,
                )
        else:
            failed = DeploymentFailedEvent(
                voyage_id=voyage_id,
                source_role=CrewRole.HELMSMAN,
                payload={**base_payload, "diagnosis": deployment.diagnosis},
            )
            try:
                await self._mushi.publish(stream_key(voyage_id), failed)
            except Exception:
                logger.warning(
                    "Failed to publish DeploymentFailedEvent for voyage %s",
                    voyage_id,
                    exc_info=True,
                )

    async def get_deployments(
        self,
        voyage_id: uuid.UUID,
        tier: DeploymentTier | None = None,
    ) -> list[Deployment]:
        stmt = select(Deployment).where(Deployment.voyage_id == voyage_id)
        if tier is not None:
            stmt = stmt.where(Deployment.tier == tier)
        stmt = stmt.order_by(Deployment.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_deployment(
        self,
        voyage_id: uuid.UUID,
        tier: DeploymentTier,
    ) -> Deployment | None:
        stmt = (
            select(Deployment)
            .where(
                Deployment.voyage_id == voyage_id,
                Deployment.tier == tier,
            )
            .order_by(Deployment.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()
