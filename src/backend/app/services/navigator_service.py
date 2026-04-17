"""NavigatorService — orchestrates Poneglyph generation from voyage plans."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crew.navigator_graph import build_navigator_graph
from app.den_den_mushi.constants import stream_key
from app.den_den_mushi.events import PoneglyphDraftedEvent
from app.den_den_mushi.mushi import DenDenMushi
from app.dial_system.router import DialSystemRouter
from app.models.enums import CrewRole, VoyageStatus
from app.models.poneglyph import Poneglyph
from app.models.vivre_card import VivreCard
from app.models.voyage import Voyage, VoyagePlan
from app.schemas.navigator import PoneglyphContentSpec

logger = logging.getLogger(__name__)


class NavigatorError(Exception):
    """Raised when Navigator agent operations fail."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class NavigatorService:
    def __init__(
        self,
        dial_router: DialSystemRouter,
        mushi: DenDenMushi,
        session: AsyncSession,
    ) -> None:
        self._dial_router = dial_router
        self._mushi = mushi
        self._session = session
        self._graph = build_navigator_graph(dial_router)

    @classmethod
    def reader(cls, session: AsyncSession) -> NavigatorService:
        """Create a read-only instance that only needs a DB session."""
        inst = cls.__new__(cls)
        inst._session = session
        inst._dial_router = None  # type: ignore[assignment]
        inst._mushi = None  # type: ignore[assignment]
        inst._graph = None  # type: ignore[assignment]
        return inst

    async def draft_poneglyphs(
        self,
        voyage: Voyage,
        plan: VoyagePlan,
    ) -> list[Poneglyph]:
        voyage.status = VoyageStatus.PDD.value
        await self._session.flush()

        plan_phases = plan.phases.get("phases", [])

        try:
            result = await self._graph.ainvoke(
                {
                    "plan_phases": plan_phases,
                    "raw_poneglyphs": "",
                    "poneglyphs": None,
                    "error": None,
                }
            )
        except Exception:
            voyage.status = VoyageStatus.CHARTED.value
            await self._session.flush()
            raise

        specs: list[PoneglyphContentSpec] | None = result.get("poneglyphs")
        if specs is None:
            voyage.status = VoyageStatus.CHARTED.value
            await self._session.flush()
            error = result.get("error", "Unknown error")
            raise NavigatorError(
                "PONEGLYPH_PARSE_FAILED",
                f"Failed to parse poneglyphs: {error}",
            )

        plan_phase_numbers = {p["phase_number"] for p in plan_phases}
        spec_phase_numbers = {s.phase_number for s in specs}
        if spec_phase_numbers != plan_phase_numbers:
            voyage.status = VoyageStatus.CHARTED.value
            await self._session.flush()
            raise NavigatorError(
                "PONEGLYPH_PHASE_MISMATCH",
                (
                    f"Poneglyph phases {sorted(spec_phase_numbers)} do not match "
                    f"plan phases {sorted(plan_phase_numbers)}"
                ),
            )

        await self._session.execute(delete(Poneglyph).where(Poneglyph.voyage_id == voyage.id))

        poneglyphs: list[Poneglyph] = []
        for spec in specs:
            p = Poneglyph(
                voyage_id=voyage.id,
                phase_number=spec.phase_number,
                content=spec.model_dump_json(),
                metadata_={
                    "phase_name": spec.title,
                    "test_criteria_count": len(spec.test_criteria),
                    "file_count": len(spec.file_paths),
                },
                created_by="navigator",
            )
            self._session.add(p)
            poneglyphs.append(p)

        card = VivreCard(
            voyage_id=voyage.id,
            crew_member="navigator",
            state_data={
                "poneglyph_count": len(poneglyphs),
                "phase_numbers": [s.phase_number for s in specs],
            },
            checkpoint_reason="poneglyphs_drafted",
        )
        self._session.add(card)

        voyage.status = VoyageStatus.CHARTED.value

        await self._session.commit()
        for p in poneglyphs:
            await self._session.refresh(p)

        # Best-effort publish events
        try:
            for p in poneglyphs:
                event = PoneglyphDraftedEvent(
                    voyage_id=voyage.id,
                    source_role=CrewRole.NAVIGATOR,
                    payload={
                        "poneglyph_id": str(p.id),
                        "phase_number": p.phase_number,
                    },
                )
                await self._mushi.publish(stream_key(voyage.id), event)
        except Exception:
            logger.warning(
                "Failed to publish poneglyph_drafted events for voyage %s",
                voyage.id,
                exc_info=True,
            )

        return poneglyphs

    async def get_poneglyphs(
        self,
        voyage_id: uuid.UUID,
    ) -> list[Poneglyph]:
        result = await self._session.execute(
            select(Poneglyph)
            .where(Poneglyph.voyage_id == voyage_id)
            .order_by(Poneglyph.phase_number)
        )
        return list(result.scalars().all())
