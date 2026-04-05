from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import ConnectionPool, Redis

from app.api.v1.router import v1_router
from app.core.config import settings
from app.core.middleware import DefaultDenyMiddleware
from app.den_den_mushi.mushi import DenDenMushi


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    app.state.redis_pool = pool
    app.state.den_den_mushi = DenDenMushi(Redis(connection_pool=pool))
    yield
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
