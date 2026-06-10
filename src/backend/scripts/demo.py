"""Run the scripted demo voyage (#56): seed a demo user + voyage and replay the
recorded event timeline through the real Den Den Mushi stream — no API key.

    python -m scripts.demo            # seed (fresh) + replay at 1x
    python -m scripts.demo --speed 2  # replay faster
    python -m scripts.demo --cleanup  # remove demo data and exit
"""

from __future__ import annotations

import argparse
import asyncio

from redis.asyncio import Redis

from app.core.config import settings
from app.demo.replayer import DemoReplayer
from app.demo.seed import DEMO_EMAIL, DEMO_PASSWORD, cleanup_demo, seed_demo
from app.den_den_mushi.mushi import DenDenMushi
from app.models import async_session, engine


async def _cleanup_only() -> None:
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        async with async_session() as session:
            removed = await cleanup_demo(session, redis)
        print(f"Removed {removed} demo voyage(s).")
    finally:
        await redis.aclose()
        await engine.dispose()


async def _run(speed: float) -> None:
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    mushi = DenDenMushi(redis)
    try:
        async with async_session() as session:
            await cleanup_demo(session, redis)  # start from a clean slate
            voyage = await seed_demo(session)

        print(f"Demo voyage seeded: {voyage.id}")
        print(f"  Log in:   http://localhost:3000/login  ({DEMO_EMAIL} / {DEMO_PASSWORD})")
        print(f"  Watch it: http://localhost:3000/app/sea-chart?voyage={voyage.id}")
        print("Replaying… (Pause/Cancel in the deck affect this replay)")

        result = await DemoReplayer(mushi, async_session, voyage.id, speed=speed).run()
        print(f"Demo {result}.")
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay the scripted demo voyage.")
    parser.add_argument("--speed", type=float, default=1.0, help="playback speed multiplier")
    parser.add_argument("--cleanup", action="store_true", help="remove demo data and exit")
    args = parser.parse_args()

    if args.cleanup:
        asyncio.run(_cleanup_only())
    else:
        asyncio.run(_run(args.speed))


if __name__ == "__main__":
    main()
