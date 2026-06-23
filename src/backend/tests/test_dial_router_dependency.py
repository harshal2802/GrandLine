"""Tests for the get_dial_router dependency resolving the per-user Claude token (C0).

The dependency reveals the voyage owner's claude_code credential from the Sea Chest
and threads it into build_router_from_config. When the user hasn't connected Claude
Code (reveal -> None), today's host behavior is preserved.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.api.v1.dependencies as deps


def _voyage(user_id: uuid.UUID) -> MagicMock:
    v = MagicMock()
    v.user_id = user_id
    return v


async def _drive(gen) -> object:
    """Run an async-generator dependency to its single yield."""
    router = await gen.__anext__()
    return router, gen


@pytest.mark.asyncio
async def test_resolves_user_token_and_threads_it() -> None:
    user_id = uuid.uuid4()
    voyage_id = uuid.uuid4()

    session = AsyncMock()
    # Session returns a non-None DialConfig from the scalar_one_or_none lookup.
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = MagicMock()  # a DialConfig stand-in
    session.execute = AsyncMock(return_value=exec_result)

    built = MagicMock()
    built.close = AsyncMock()

    with (
        patch.object(deps, "SeaChestService") as sea_cls,
        patch.object(deps, "build_router_from_config", return_value=built) as build,
        patch.object(deps, "RateLimiter", MagicMock()),
    ):
        sea_cls.return_value.reveal = AsyncMock(return_value="sk-ant-user")

        gen = deps.get_dial_router(
            voyage_id=voyage_id,
            session=session,
            voyage=_voyage(user_id),
            mushi=MagicMock(),
            redis=MagicMock(),
        )
        router, gen = await _drive(gen)

    assert router is built
    # The token was revealed for the voyage OWNER under kind claude_code.
    sea_cls.return_value.reveal.assert_awaited_once_with(user_id, "claude_code")
    # ...and threaded into the router build.
    assert build.call_args.kwargs["claude_code_oauth_token"] == "sk-ant-user"


@pytest.mark.asyncio
async def test_no_credential_passes_none() -> None:
    user_id = uuid.uuid4()
    session = AsyncMock()
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = MagicMock()
    session.execute = AsyncMock(return_value=exec_result)

    built = MagicMock()
    built.close = AsyncMock()

    with (
        patch.object(deps, "SeaChestService") as sea_cls,
        patch.object(deps, "build_router_from_config", return_value=built) as build,
        patch.object(deps, "RateLimiter", MagicMock()),
    ):
        sea_cls.return_value.reveal = AsyncMock(return_value=None)

        gen = deps.get_dial_router(
            voyage_id=uuid.uuid4(),
            session=session,
            voyage=_voyage(user_id),
            mushi=MagicMock(),
            redis=MagicMock(),
        )
        await _drive(gen)

    assert build.call_args.kwargs["claude_code_oauth_token"] is None
