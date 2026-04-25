import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import ConnectionPool, Redis

from app.api.v1.router import v1_router
from app.core.config import settings
from app.core.middleware import DefaultDenyMiddleware
from app.den_den_mushi.mushi import DenDenMushi
from app.deployment.in_process import InProcessDeploymentBackend
from app.execution.factory import create_backend, create_git_backend
from app.services.execution_service import ExecutionService
from app.services.git_service import GitService

logger = logging.getLogger(__name__)

_PIPELINE_SHUTDOWN_TIMEOUT_S = 5.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    app.state.redis_pool = pool
    app.state.den_den_mushi = DenDenMushi(Redis(connection_pool=pool))

    backend = create_backend(settings)
    app.state.execution_service = ExecutionService(backend)

    git_backend = create_git_backend(settings)
    app.state.git_service = GitService(git_backend, settings)

    app.state.deployment_backend = InProcessDeploymentBackend()

    # Process-local registry of in-flight pipeline tasks. Keyed by voyage_id.
    # Multi-worker deployments are out of scope for v1 (single-worker fleet).
    pipeline_tasks: dict[uuid.UUID, asyncio.Task[None]] = {}
    app.state.pipeline_tasks = pipeline_tasks

    yield

    # Cancel in-flight pipeline tasks and give them a short window to emit
    # terminal events (e.g. PipelineFailedEvent) before the loop tears down.
    pending = [t for t in app.state.pipeline_tasks.values() if not t.done()]
    for task in pending:
        task.cancel()
    if pending:
        done, still_pending = await asyncio.wait(pending, timeout=_PIPELINE_SHUTDOWN_TIMEOUT_S)
        if still_pending:
            logger.warning(
                "Shutdown: %d pipeline task(s) did not finish within %.1fs",
                len(still_pending),
                _PIPELINE_SHUTDOWN_TIMEOUT_S,
            )

    await app.state.deployment_backend.close()
    await app.state.git_service.cleanup_all()
    await git_backend.close()
    await app.state.execution_service.cleanup_all()
    await backend.close()
    await pool.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(DefaultDenyMiddleware)

    app.include_router(v1_router)

    return app


app = create_app()
