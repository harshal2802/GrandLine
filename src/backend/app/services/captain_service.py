"""CaptainService — orchestrates voyage plan creation."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crew.captain_graph import build_captain_graph
from app.den_den_mushi.constants import stream_key
from app.den_den_mushi.events import VoyagePlanCreatedEvent
from app.den_den_mushi.mushi import DenDenMushi
from app.dial_system.router import DialSystemRouter
from app.models.enums import CrewRole, VoyageStatus
from app.models.vivre_card import VivreCard
from app.models.voyage import Voyage, VoyagePlan
from app.schemas.captain import VoyagePlanSpec

logger = logging.getLogger(__name__)


class CaptainError(Exception):
    """Raised when Captain agent operations fail."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class CaptainService:
    def __init__(
        self,
        dial_router: DialSystemRouter,
        mushi: DenDenMushi,
        session: AsyncSession,
    ) -> None:
        self._dial_router = dial_router
        self._mushi = mushi
        self._session = session
        self._graph = build_captain_graph(dial_router)

    async def chart_course(
        self,
        voyage: Voyage,
        task: str,
    ) -> tuple[VoyagePlan, VoyagePlanSpec]:
        voyage.status = VoyageStatus.PLANNING.value
        await self._session.flush()

        try:
            result = await self._graph.ainvoke(
                {
                    "task": task,
                    "raw_plan": "",
                    "plan": None,
                    "error": None,
                }
            )
        except Exception:
            # Fix #8: reset status so the voyage isn't stuck in PLANNING
            voyage.status = VoyageStatus.CHARTED.value
            await self._session.flush()
            raise

        spec: VoyagePlanSpec | None = result.get("plan")
        if spec is None:
            # Fix #8: reset status on parse failure too
            voyage.status = VoyageStatus.CHARTED.value
            await self._session.flush()
            error = result.get("error", "Unknown error")
            raise CaptainError(
                "PLAN_PARSE_FAILED",
                f"Failed to parse voyage plan: {error}",
            )

        # Determine next version
        latest = await self._get_latest_plan(voyage.id)
        next_version = (latest.version + 1) if latest else 1

        plan = VoyagePlan(
            voyage_id=voyage.id,
            phases=spec.model_dump(),
            created_by="captain",
            version=next_version,
        )
        self._session.add(plan)

        # Fix #2: inline checkpoint creation so all DB writes
        # commit together in one transaction
        card = VivreCard(
            voyage_id=voyage.id,
            crew_member="captain",
            state_data={
                "task": task,
                "plan_version": next_version,
                "phase_count": len(spec.phases),
            },
            checkpoint_reason="plan_created",
        )
        self._session.add(card)

        await self._session.commit()
        await self._session.refresh(plan)

        # Publish event after commit — fire-and-forget
        event = VoyagePlanCreatedEvent(
            voyage_id=voyage.id,
            source_role=CrewRole.CAPTAIN,
            payload={
                "plan_id": str(plan.id),
                "version": next_version,
                "phase_count": len(spec.phases),
            },
        )
        await self._mushi.publish(stream_key(voyage.id), event)

        return plan, spec

    async def get_plan(
        self,
        voyage_id: uuid.UUID,
    ) -> VoyagePlan | None:
        result = await self._session.execute(
            select(VoyagePlan)
            .where(VoyagePlan.voyage_id == voyage_id)
            .order_by(VoyagePlan.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_latest_plan(
        self,
        voyage_id: uuid.UUID,
    ) -> VoyagePlan | None:
        return await self.get_plan(voyage_id)
