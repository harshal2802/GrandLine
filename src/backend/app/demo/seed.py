"""Seed + teardown for the demo voyage (#56).

Creates a loginable demo user and a clearly-badged demo voyage (plus a dial
config so the Dial panel renders). The replayer drives everything else through
the event stream; nothing here needs an API key. `cleanup_demo` removes the
seeded rows and the Redis event stream.
"""

from __future__ import annotations

import uuid

from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.demo.replayer import DEMO_TARGET_REPO
from app.den_den_mushi.constants import stream_key
from app.models.dial_config import DialConfig
from app.models.user import User
from app.models.voyage import Voyage

DEMO_EMAIL = "demo@grandline.io"
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo-voyage"
DEMO_TITLE = "🎬 Demo Voyage — Telemetry Pipeline"

_DEMO_DIAL_MAPPING = {
    role: {"provider": "anthropic", "model": "claude-sonnet-4-20250514"}
    for role in ("captain", "navigator", "shipwright", "doctor", "helmsman")
}


async def _get_or_create_demo_user(session: AsyncSession) -> User:
    existing = (
        await session.execute(select(User).where(User.email == DEMO_EMAIL))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    user = User(
        id=uuid.uuid4(),
        email=DEMO_EMAIL,
        username=DEMO_USERNAME,
        hashed_password=hash_password(DEMO_PASSWORD),
    )
    session.add(user)
    await session.flush()
    return user


async def seed_demo(session: AsyncSession) -> Voyage:
    """Create a fresh demo voyage (CHARTED, 4 pending phases) owned by the demo
    user. Returns the voyage."""
    user = await _get_or_create_demo_user(session)

    voyage = Voyage(
        id=uuid.uuid4(),
        user_id=user.id,
        title=DEMO_TITLE,
        description="A scripted voyage replayed through the real stack — no API key needed.",
        status="CHARTED",
        target_repo=DEMO_TARGET_REPO,
        phase_status={"1": "PENDING", "2": "PENDING", "3": "PENDING", "4": "PENDING"},
    )
    session.add(voyage)

    session.add(
        DialConfig(
            id=uuid.uuid4(),
            voyage_id=voyage.id,
            role_mapping=_DEMO_DIAL_MAPPING,
            fallback_chain={"captain": [{"provider": "openai", "model": "gpt-4o"}]},
        )
    )

    await session.commit()
    await session.refresh(voyage)
    return voyage


async def cleanup_demo(session: AsyncSession, redis: Redis | None = None) -> int:
    """Delete all seeded demo voyages (by marker), their dial configs, the demo
    user, and the Redis event streams. Returns the number of voyages removed."""
    voyages = (
        (await session.execute(select(Voyage).where(Voyage.target_repo == DEMO_TARGET_REPO)))
        .scalars()
        .all()
    )
    for voyage in voyages:
        await session.execute(delete(DialConfig).where(DialConfig.voyage_id == voyage.id))
        if redis is not None:
            await redis.delete(stream_key(voyage.id))
    for voyage in voyages:
        await session.delete(voyage)

    # Remove the demo user once its voyages are gone.
    user = (
        await session.execute(select(User).where(User.email == DEMO_EMAIL))
    ).scalar_one_or_none()
    if user is not None:
        remaining = (
            await session.execute(select(Voyage.id).where(Voyage.user_id == user.id))
        ).first()
        if remaining is None:
            await session.delete(user)

    await session.commit()
    return len(voyages)
