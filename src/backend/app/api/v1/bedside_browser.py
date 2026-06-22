"""Bedside Browser REST API (Phase 23) — Doctor browser-in-the-loop verification.

``POST /api/v1/voyages/{voyage_id}/phases/{phase_number}/browser-check`` runs a
``BrowserCheckSpec`` through the configured ``BrowserCheckBackend`` (the Null
default, or Playwright when opted in), persists a ``BrowserCheck``, and records a
``BROWSER_CHECK_RUN`` CrewAction so the Ship's Log surfaces the screenshot.
``GET /api/v1/voyages/{voyage_id}/browser-checks`` lists a voyage's runs.

Default-deny: requires an authenticated user; the voyage is owner-scoped via
``get_authorized_voyage`` (a missing or foreign voyage is 404).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import (
    get_authorized_voyage,
    get_browser_backend,
    get_current_user,
    get_den_den_mushi,
)
from app.browser.backend import BrowserCheckBackend
from app.den_den_mushi.mushi import DenDenMushi
from app.models import get_db
from app.models.user import User
from app.models.voyage import Voyage
from app.schemas.browser_check import BrowserCheckRead, BrowserCheckSpec
from app.services.bedside_browser_service import BedsideBrowserService

router = APIRouter(prefix="/voyages/{voyage_id}", tags=["bedside-browser"])


async def get_bedside_browser_service(
    session: AsyncSession = Depends(get_db),
    mushi: DenDenMushi = Depends(get_den_den_mushi),
) -> BedsideBrowserService:
    return BedsideBrowserService(session, mushi)


async def get_bedside_browser_reader(
    session: AsyncSession = Depends(get_db),
) -> BedsideBrowserService:
    return BedsideBrowserService(session)


@router.post(
    "/phases/{phase_number}/browser-check",
    response_model=BrowserCheckRead,
    status_code=status.HTTP_201_CREATED,
)
async def run_browser_check(
    voyage_id: uuid.UUID,
    phase_number: int,
    spec: BrowserCheckSpec,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    service: BedsideBrowserService = Depends(get_bedside_browser_service),
    backend: BrowserCheckBackend = Depends(get_browser_backend),
) -> BrowserCheckRead:
    check = await service.run_browser_check(voyage, phase_number, spec, backend)
    return BrowserCheckRead.model_validate(check)


@router.get("/browser-checks", response_model=list[BrowserCheckRead])
async def list_browser_checks(
    voyage_id: uuid.UUID,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    service: BedsideBrowserService = Depends(get_bedside_browser_reader),
) -> list[BrowserCheckRead]:
    checks = await service.list_browser_checks(voyage_id)
    return [BrowserCheckRead.model_validate(c) for c in checks]
