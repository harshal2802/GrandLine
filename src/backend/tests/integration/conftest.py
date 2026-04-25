"""Fixtures for the pipeline integration test suite.

Required infra (matches `pdd/prompts/features/pipeline/grandline-15-05-integration.md`):
- Postgres on localhost:5432, db `grandline`, user/pass `grandline`/`grandline`
  (same db the dev backend uses; migrations applied via `make migrate`)
- Redis on localhost:6379 db **index 1** (not 0 — that's dev data)

Each fixture skips cleanly if the underlying service is unreachable, so the
suite can be run as `pytest -m integration` from any developer machine.

Pipeline tables are TRUNCATE'd CASCADE on both fixture entry and exit so the
test order does not matter and no data is leaked into the shared dev DB.
"""

from __future__ import annotations

import socket
import uuid
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.den_den_mushi.mushi import DenDenMushi
from app.deployment.in_process import InProcessDeploymentBackend
from app.execution.backend import ExecutionBackend
from app.services.execution_service import ExecutionService
from app.services.git_service import GitService
from tests.integration.stubs import StubExecutionBackend

# Use the same psycopg v3 driver the app is built on. The
# `postgresql+psycopg://` scheme transparently supports async via
# `create_async_engine` (psycopg's async API), so no extra dependency.
_INTEGRATION_DB_URL = "postgresql+psycopg://grandline:grandline@localhost:5432/grandline"
_REDIS_URL = "redis://localhost:6379/1"

_TRUNCATE_SQL = text(
    "TRUNCATE deployments, validation_runs, build_artifacts, shipwright_runs, "
    "health_checks, poneglyphs, voyage_plans, voyages, dial_configs, "
    "vivre_cards, crew_actions, users RESTART IDENTITY CASCADE"
)


def _postgres_reachable() -> bool:
    try:
        with socket.create_connection(("localhost", 5432), timeout=0.5):
            return True
    except OSError:
        return False


async def _redis_reachable() -> bool:
    try:
        client = Redis.from_url(_REDIS_URL, decode_responses=True)
        try:
            await client.ping()
        finally:
            await client.aclose()
        return True
    except (RedisConnectionError, OSError):
        return False


@pytest.fixture
async def integration_engine() -> AsyncIterator[AsyncEngine]:
    """Async engine pointed at the dev Postgres.

    Function-scoped to keep within pytest-asyncio's per-test loop. The dev DB
    is local so the per-test reconnect cost is negligible (~5ms).
    Skips the test if Postgres is unreachable.
    """
    if not _postgres_reachable():
        pytest.skip("Postgres not available on localhost:5432")
    engine = create_async_engine(_INTEGRATION_DB_URL, echo=False, future=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def integration_session_factory(
    integration_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Session factory bound to the integration engine.

    Used by `_build_one_phase` to open a per-phase session (issue #39).
    """
    return async_sessionmaker(integration_engine, expire_on_commit=False)


@pytest.fixture
async def db_session(
    integration_engine: AsyncEngine,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Truncate all pipeline tables, yield a session, truncate again on teardown."""
    # Pre-test cleanup so we never inherit a previous failed run's data.
    async with integration_engine.begin() as conn:
        await conn.execute(_TRUNCATE_SQL)

    async with integration_session_factory() as session:
        yield session

    # Post-test cleanup runs even if the test or the assertions fail.
    async with integration_engine.begin() as conn:
        await conn.execute(_TRUNCATE_SQL)


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    """Redis db=1 client. flushdb on teardown. Skip cleanly if unreachable."""
    client = Redis.from_url(_REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except (RedisConnectionError, OSError):
        pytest.skip("Redis not available on localhost:6379")
    # Pre-test flush so we don't see leftovers from a prior failed run.
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest.fixture
def mushi(redis_client: Redis) -> DenDenMushi:
    return DenDenMushi(redis_client)


@pytest.fixture
def stub_execution_backend() -> ExecutionBackend:
    return StubExecutionBackend()


@pytest.fixture
def stub_execution_service(
    stub_execution_backend: ExecutionBackend,
) -> ExecutionService:
    return ExecutionService(stub_execution_backend)


@pytest.fixture
def stub_git_service() -> GitService | None:
    """Tests pass `None` for the git service — the in-process deploy backend
    does not need it and avoiding `GitService` keeps the surface tiny."""
    return None


@pytest.fixture
def stub_deployment_backend() -> InProcessDeploymentBackend:
    return InProcessDeploymentBackend()


@pytest.fixture
def voyage_id() -> uuid.UUID:
    """A fresh voyage id per test."""
    return uuid.uuid4()
