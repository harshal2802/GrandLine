import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import ConnectionPool, Redis

from app.api.v1.router import v1_router
from app.browser.factory import create_browser_backend
from app.cabin.factory import create_cabin_backend
from app.core.config import settings
from app.core.middleware import DefaultDenyMiddleware
from app.den_den_mushi.mushi import DenDenMushi
from app.deployment.in_process import InProcessDeploymentBackend
from app.execution.factory import create_backend, create_git_backend
from app.services.cabin_service import CabinService
from app.services.execution_service import ExecutionService
from app.services.git_service import GitService
from app.services.preview_service import PreviewService

logger = logging.getLogger(__name__)

_PIPELINE_SHUTDOWN_TIMEOUT_S = 5.0

# Methods/headers the API actually uses; anything else is rejected by CORS
# preflight instead of being blanket-allowed.
_CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
_CORS_ALLOW_HEADERS = ["Authorization", "Content-Type"]

_DEFAULT_JWT_SECRET = "change-me-in-production"


async def _cabin_reaper_loop(cabin_service: CabinService, preview_service: PreviewService) -> None:
    """Periodically reap idle/over-lifetime Cabins AND over-lifetime previews.

    Preview reaping piggybacks on the existing Cabin reaper cadence: a preview is a
    long-running, credential-bearing process, so it must never outlive its hard max
    lifetime — ``reap_expired`` stops any past the cap (no orphan processes).
    """
    interval = settings.cabin_reap_interval_seconds
    while True:
        try:
            await asyncio.sleep(interval)
            reaped = await cabin_service.reap_idle()
            if reaped:
                logger.info("Cabin reaper destroyed %d idle/expired cabin(s)", len(reaped))
            reaped_previews = await preview_service.reap_expired()
            if reaped_previews:
                logger.info(
                    "Preview reaper stopped %d over-lifetime preview(s)",
                    len(reaped_previews),
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Cabin reaper loop iteration failed", exc_info=True)


def validate_production_settings() -> None:
    """Refuse to boot with insecure defaults outside debug mode.

    Dev flows (docker-compose, `make api-dev`) set GRANDLINE_DEBUG=true and
    are unaffected. Production (debug=false) must configure a real secret.
    """
    if settings.debug:
        return
    if settings.jwt_secret_key == _DEFAULT_JWT_SECRET:
        raise RuntimeError(
            "GRANDLINE_JWT_SECRET_KEY is still the insecure default "
            f"({_DEFAULT_JWT_SECRET!r}). Set a strong secret, or set "
            "GRANDLINE_DEBUG=true for local development."
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Runs at serve time (uvicorn), not at import time, so tests can import
    # the app object without production-grade settings.
    validate_production_settings()

    pool = ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    app.state.redis_pool = pool
    app.state.den_den_mushi = DenDenMushi(Redis(connection_pool=pool))

    backend = create_backend(settings)
    app.state.execution_service = ExecutionService(backend)

    git_backend = create_git_backend(settings)
    app.state.git_service = GitService(git_backend, settings)

    app.state.deployment_backend = InProcessDeploymentBackend()

    app.state.browser_backend = create_browser_backend(settings)

    # Cabin (Phase 0b): the per-user persistent sandbox. Like the pipeline-task
    # registry, the Cabin registry is process-local (v1 single-worker).
    cabin_service = CabinService(create_cabin_backend(settings), settings)
    app.state.cabin_service = cabin_service

    # Live App preview (Phase B0): a standalone service over the Cabin that runs the
    # crew's built app as a long-running process inside the user's Cabin. It leaves the
    # pipeline's InProcessDeploymentBackend untouched. Process-local registry, v1
    # single-worker (like the Cabin registry / pipeline_tasks).
    preview_service = PreviewService(cabin_service, settings)
    app.state.preview_service = preview_service

    # Background idle reaper: destroys Cabins idle past the timeout OR past the hard
    # max lifetime, and stops previews past their hard lifetime cap. Cancelled +
    # awaited on shutdown, mirroring the pipeline-task drain.
    reaper_task = asyncio.create_task(_cabin_reaper_loop(cabin_service, preview_service))

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

    # Stop the Cabin reaper, then stop every preview (no orphan processes) and tear
    # down the Cabins it manages.
    reaper_task.cancel()
    try:
        await reaper_task
    except asyncio.CancelledError:
        pass
    await preview_service.stop_all()
    await cabin_service.cleanup_all()
    await cabin_service.close()

    await app.state.deployment_backend.close()
    await app.state.browser_backend.close()
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
        allow_methods=_CORS_ALLOW_METHODS,
        allow_headers=_CORS_ALLOW_HEADERS,
    )
    app.add_middleware(DefaultDenyMiddleware)

    app.include_router(v1_router)

    return app


app = create_app()
