"""Standing Orders REST API — reusable voyage presets, owner-scoped.

Default-deny: every endpoint requires an authenticated user, and every operation
is scoped to the requesting user's own Standing Orders. ``POST /{id}/chart``
stamps a preset into a fresh voyage (status CHARTED), applying the preset's dial
config and repo/context defaults.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user
from app.models import get_db
from app.models.user import User
from app.schemas.standing_order import (
    ChartFromStandingOrderRequest,
    StandingOrderCreate,
    StandingOrderRead,
    StandingOrderUpdate,
)
from app.schemas.voyage import VoyageRead
from app.services.standing_order_service import StandingOrderError, StandingOrderService

router = APIRouter(prefix="/standing-orders", tags=["standing-orders"])


async def get_standing_order_service(
    session: AsyncSession = Depends(get_db),
) -> StandingOrderService:
    return StandingOrderService(session)


def _not_found(exc: StandingOrderError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": {"code": exc.code, "message": exc.message}},
    )


@router.get("", response_model=list[StandingOrderRead])
async def list_standing_orders(
    user: User = Depends(get_current_user),
    service: StandingOrderService = Depends(get_standing_order_service),
) -> list[StandingOrderRead]:
    """List the requesting user's Standing Orders (newest first)."""
    orders = await service.list_for_user(user.id)
    return [StandingOrderRead.model_validate(o) for o in orders]


@router.post("", response_model=StandingOrderRead, status_code=status.HTTP_201_CREATED)
async def create_standing_order(
    body: StandingOrderCreate,
    user: User = Depends(get_current_user),
    service: StandingOrderService = Depends(get_standing_order_service),
) -> StandingOrderRead:
    """Create a new Standing Order (a reusable voyage preset)."""
    order = await service.create(
        user.id,
        name=body.name,
        description=body.description,
        target_repo=body.target_repo,
        dial_config=body.dial_config,
        plan_skeleton=body.plan_skeleton,
        injected_context=body.injected_context,
    )
    return StandingOrderRead.model_validate(order)


@router.get("/{order_id}", response_model=StandingOrderRead)
async def get_standing_order(
    order_id: uuid.UUID,
    user: User = Depends(get_current_user),
    service: StandingOrderService = Depends(get_standing_order_service),
) -> StandingOrderRead:
    """Fetch one of the requesting user's Standing Orders."""
    try:
        order = await service.get(order_id, user.id)
    except StandingOrderError as exc:
        raise _not_found(exc)
    return StandingOrderRead.model_validate(order)


@router.patch("/{order_id}", response_model=StandingOrderRead)
async def update_standing_order(
    order_id: uuid.UUID,
    body: StandingOrderUpdate,
    user: User = Depends(get_current_user),
    service: StandingOrderService = Depends(get_standing_order_service),
) -> StandingOrderRead:
    """Apply a partial update to an owned Standing Order."""
    fields = body.model_dump(exclude_unset=True)
    try:
        order = await service.update(order_id, user.id, fields=fields)
    except StandingOrderError as exc:
        raise _not_found(exc)
    return StandingOrderRead.model_validate(order)


@router.delete(
    "/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_standing_order(
    order_id: uuid.UUID,
    user: User = Depends(get_current_user),
    service: StandingOrderService = Depends(get_standing_order_service),
) -> Response:
    """Delete an owned Standing Order."""
    try:
        await service.delete(order_id, user.id)
    except StandingOrderError as exc:
        raise _not_found(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{order_id}/chart",
    response_model=VoyageRead,
    status_code=status.HTTP_201_CREATED,
)
async def chart_from_standing_order(
    order_id: uuid.UUID,
    body: ChartFromStandingOrderRequest,
    user: User = Depends(get_current_user),
    service: StandingOrderService = Depends(get_standing_order_service),
) -> VoyageRead:
    """Chart a voyage from a Standing Order, applying the preset's config."""
    try:
        order = await service.get(order_id, user.id)
    except StandingOrderError as exc:
        raise _not_found(exc)
    voyage = await service.chart(
        order,
        task=body.task,
        title=body.title,
        target_repo=body.target_repo,
    )
    return VoyageRead.model_validate(voyage)
