from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_authorized_voyage, get_dial_router, get_redis
from app.dial_system.rate_limiter import WINDOW_SECONDS, RateLimiter
from app.dial_system.router import DialSystemRouter
from app.models import get_db
from app.models.dial_config import DialConfig
from app.models.voyage import Voyage
from app.schemas.dial_config import DialConfigRead, DialConfigUpdate
from app.schemas.dial_system import (
    CompletionRequest,
    CompletionResult,
    DialStatusResponse,
    ProviderWindowUsage,
)

router = APIRouter(prefix="/voyages", tags=["dial-system"])


def _canonical_provider(provider: str) -> str:
    """Match DialSystemRouter._get_provider_name so rate-limit keys line up.

    The factory accepts the ``claude-code`` alias, but the router records and
    enforces usage under ``claude_code`` — report headroom under the same name.
    """
    return "claude_code" if provider in ("claude_code", "claude-code") else provider


def _providers_in_config(
    role_mapping: dict[str, Any] | None, fallback_chain: dict[str, Any] | None
) -> list[str]:
    """Distinct provider names referenced by a dial config (mapping + fallbacks)."""
    providers: set[str] = set()
    for cfg in (role_mapping or {}).values():
        if isinstance(cfg, dict) and cfg.get("provider"):
            providers.add(_canonical_provider(str(cfg["provider"])))
    for entries in (fallback_chain or {}).values():
        for entry in entries or []:
            if isinstance(entry, str):
                providers.add(_canonical_provider(entry))
            elif isinstance(entry, dict) and entry.get("provider"):
                providers.add(_canonical_provider(str(entry["provider"])))
    return sorted(providers)


@router.get("/{voyage_id}/dial-config", response_model=DialConfigRead)
async def get_dial_config(
    voyage_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _voyage: Voyage = Depends(get_authorized_voyage),
) -> DialConfig:
    result = await session.execute(select(DialConfig).where(DialConfig.voyage_id == voyage_id))
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="Dial config not found for this voyage")
    return config


@router.put("/{voyage_id}/dial-config", response_model=DialConfigRead)
async def update_dial_config(
    voyage_id: uuid.UUID,
    body: DialConfigUpdate,
    session: AsyncSession = Depends(get_db),
    _voyage: Voyage = Depends(get_authorized_voyage),
) -> DialConfig:
    result = await session.execute(select(DialConfig).where(DialConfig.voyage_id == voyage_id))
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="Dial config not found for this voyage")

    if body.role_mapping is not None:
        config.role_mapping = body.role_mapping
    if body.fallback_chain is not None:
        config.fallback_chain = body.fallback_chain

    await session.commit()
    await session.refresh(config)
    return config


@router.get("/{voyage_id}/dial-status", response_model=DialStatusResponse)
async def get_dial_status(
    voyage_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    _voyage: Voyage = Depends(get_authorized_voyage),
) -> DialStatusResponse:
    """Per-provider rate-limit headroom for the current sliding window (read-only).

    Lets the deck show how much request/token budget each configured provider
    has left, and pre-warn before a trip. Reuses the same RateLimiter the router
    consults; no routing/failover logic is touched.
    """
    result = await session.execute(select(DialConfig).where(DialConfig.voyage_id == voyage_id))
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="Dial config not found for this voyage")

    limiter = RateLimiter(redis)
    providers: list[ProviderWindowUsage] = []
    for provider in _providers_in_config(config.role_mapping, config.fallback_chain):
        st = await limiter.check(provider)
        providers.append(
            ProviderWindowUsage(
                provider=provider,
                is_limited=st.is_limited,
                remaining_requests=st.remaining_requests,
                remaining_tokens=st.remaining_tokens,
                max_requests=limiter.max_requests,
                max_tokens=limiter.max_tokens,
            )
        )

    return DialStatusResponse(
        voyage_id=voyage_id, window_seconds=WINDOW_SECONDS, providers=providers
    )


@router.post(
    "/{voyage_id}/completions",
    response_model=CompletionResult,
)
async def create_completion(
    voyage_id: uuid.UUID,
    body: CompletionRequest,
    dial_router: DialSystemRouter = Depends(get_dial_router),
) -> CompletionResult:
    return await dial_router.route(body.role, body)


@router.post("/{voyage_id}/completions/stream")
async def create_completion_stream(
    voyage_id: uuid.UUID,
    body: CompletionRequest,
    dial_router: DialSystemRouter = Depends(get_dial_router),
) -> StreamingResponse:
    async def generate() -> AsyncIterator[str]:
        async for token in dial_router.stream(body.role, body):
            yield f"data: {token}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
