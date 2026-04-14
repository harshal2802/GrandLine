"""CaptainService — orchestrates voyage plan creation."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.captain_graph import build_captain_graph
from app.den_den_mushi.constants import stream_key
from app.den_den_mushi.events import VoyagePlanCreatedEvent
from app.den_den_mushi.mushi import DenDenMushi
from app.dial_system.router import DialSystemRouter
from app.models.enums import CrewRole, VoyageStatus
from app.models.voyage import Voyage, VoyagePlan
from app.schemas.captain import VoyagePlanSpec
from app.services.vivre_card_service import checkpoint as vivre_card_checkpoint


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

    async def chart_course(
        self,
        voyage: Voyage,
        task: str,
    ) -> tuple[VoyagePlan, VoyagePlanSpec]:
        voyage.status = VoyageStatus.PLANNING.value
        await self._session.flush()

        graph = build_captain_graph(self._dial_router)
        result = await graph.ainvoke(
            {
                "task": task,
                "raw_plan": "",
                "plan": None,
                "error": None,
            }
        )

        spec: VoyagePlanSpec | None = result.get("plan")
        if spec is None:
            error = result.get("error", "Unknown error")
            raise ValueError(f"Failed to parse voyage plan: {error}")

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
        await self._session.flush()
        await self._session.refresh(plan)

        # Checkpoint captain state
        await vivre_card_checkpoint(
            self._session,
            voyage.id,
            "captain",
            {
                "task": task,
                "plan_version": next_version,
                "phase_count": len(spec.phases),
            },
            "plan_created",
        )

        # Publish event
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
