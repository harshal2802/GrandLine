"""StandingOrderService — manage reusable voyage presets and chart from them.

A Standing Order is a per-user, named bundle of ``{dial config + optional plan
skeleton + injected context + default target repo}``. This service owns CRUD over
those presets (owner-scoped throughout) plus ``chart`` — which stamps a preset
into a fresh Voyage the same way ``voyages.py`` does, but seeds the voyage's
DialConfig from the preset (when present) instead of the deployment default.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.voyages import _default_dial_config
from app.models.dial_config import DialConfig
from app.models.enums import VoyageStatus
from app.models.standing_order import StandingOrder
from app.models.voyage import Voyage


class StandingOrderError(Exception):
    """Raised when a Standing Order operation fails (e.g. not found / not owned)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class StandingOrderService:
    """CRUD over Standing Orders plus charting a voyage from a preset."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def reader(cls, session: AsyncSession) -> StandingOrderService:
        """Create a session-only instance (mirrors other services' ``reader``)."""
        return cls(session)

    async def create(
        self,
        user_id: uuid.UUID,
        *,
        name: str,
        description: str | None = None,
        target_repo: str | None = None,
        dial_config: dict[str, Any] | None = None,
        plan_skeleton: dict[str, Any] | None = None,
        injected_context: str | None = None,
    ) -> StandingOrder:
        """Persist a new Standing Order owned by ``user_id``."""
        order = StandingOrder(
            id=uuid.uuid4(),
            user_id=user_id,
            name=name,
            description=description,
            target_repo=target_repo,
            dial_config=dial_config,
            plan_skeleton=plan_skeleton,
            injected_context=injected_context,
        )
        self._session.add(order)
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(order)
        return order

    async def get(self, order_id: uuid.UUID, user_id: uuid.UUID) -> StandingOrder:
        """Return an owned Standing Order or raise ``NOT_FOUND``.

        Owner-scoping is enforced in the query so a foreign id is indistinguishable
        from a missing one (no existence leak).
        """
        result = await self._session.execute(
            select(StandingOrder).where(
                StandingOrder.id == order_id,
                StandingOrder.user_id == user_id,
            )
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise StandingOrderError("NOT_FOUND", "Standing Order not found")
        return order

    async def list_for_user(self, user_id: uuid.UUID) -> list[StandingOrder]:
        """Return all Standing Orders owned by ``user_id`` (newest first)."""
        result = await self._session.execute(
            select(StandingOrder)
            .where(StandingOrder.user_id == user_id)
            .order_by(StandingOrder.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(
        self,
        order_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        fields: dict[str, Any],
    ) -> StandingOrder:
        """Apply a partial update to an owned Standing Order.

        ``fields`` is the set of provided (non-omitted) attributes; only those are
        written so PATCH can leave other columns untouched.
        """
        order = await self.get(order_id, user_id)
        for key, value in fields.items():
            setattr(order, key, value)
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(order)
        return order

    async def delete(self, order_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Delete an owned Standing Order (raises ``NOT_FOUND`` if not owned)."""
        order = await self.get(order_id, user_id)
        await self._session.delete(order)
        await self._session.commit()

    async def chart(
        self,
        order: StandingOrder,
        *,
        task: str,
        title: str | None = None,
        target_repo: str | None = None,
    ) -> Voyage:
        """Chart a voyage from a Standing Order.

        Mirrors ``voyages.create_voyage``: creates a ``CHARTED`` voyage and seeds a
        ``DialConfig`` in one atomic commit. The preset's ``dial_config`` bundle is
        applied when present; otherwise the voyage gets the SAME default
        ``voyages.py`` uses, so the two charting paths never diverge. The preset's
        ``injected_context`` (when set) is prepended to the voyage description so
        the framing travels with the voyage rather than being silently dropped.
        """
        chosen_repo = target_repo if target_repo is not None else order.target_repo
        chosen_title = title if title is not None else order.name
        description = self._compose_description(order.injected_context, task)

        voyage = Voyage(
            id=uuid.uuid4(),
            user_id=order.user_id,
            title=chosen_title,
            description=description,
            target_repo=chosen_repo,
            status=VoyageStatus.CHARTED.value,
            phase_status={},
        )
        self._session.add(voyage)
        await self._session.flush()

        self._session.add(self._dial_config_for(order, voyage.id))

        await self._session.commit()
        await self._session.refresh(voyage)
        return voyage

    @staticmethod
    def _compose_description(injected_context: str | None, task: str) -> str:
        """Prepend the order's injected context to the voyage description.

        With no injected context the task stands alone; with it, the framing
        leads, separated by a markdown rule — never silently dropped.
        """
        if injected_context:
            return f"{injected_context}\n\n---\n\n{task}"
        return task

    @staticmethod
    def _dial_config_for(order: StandingOrder, voyage_id: uuid.UUID) -> DialConfig:
        """Build the charted voyage's DialConfig from the preset or the default."""
        if order.dial_config:
            return DialConfig(
                id=uuid.uuid4(),
                voyage_id=voyage_id,
                role_mapping=order.dial_config.get("role_mapping", {}),
                fallback_chain=order.dial_config.get("fallback_chain"),
            )
        return _default_dial_config(voyage_id)
