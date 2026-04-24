from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import JWTError, decode_token
from app.den_den_mushi.mushi import DenDenMushi
from app.deployment.backend import DeploymentBackend
from app.dial_system.factory import build_router_from_config
from app.dial_system.rate_limiter import RateLimiter
from app.dial_system.router import DialSystemRouter
from app.models import get_db
from app.models.dial_config import DialConfig
from app.models.user import User
from app.models.voyage import Voyage
from app.services.execution_service import ExecutionService
from app.services.git_service import GitService
from app.services.pipeline_service import PipelineService

bearer_scheme = HTTPBearer(auto_error=False)


async def get_redis() -> AsyncGenerator[Redis, None]:
    client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


def get_den_den_mushi(request: Request) -> DenDenMushi:
    mushi: DenDenMushi = request.app.state.den_den_mushi
    return mushi


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "NOT_AUTHENTICATED",
                    "message": "Missing authentication token",
                }
            },
        )

    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid or expired token"}},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_TOKEN",
                    "message": "Token is not an access token",
                }
            },
        )

    user_id = uuid.UUID(payload["sub"])
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "USER_NOT_FOUND", "message": "User not found or inactive"}},
        )

    return user


async def get_authorized_voyage(
    voyage_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Voyage:
    result = await session.execute(
        select(Voyage).where(Voyage.id == voyage_id, Voyage.user_id == user.id)
    )
    voyage = result.scalar_one_or_none()
    if voyage is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voyage not found",
        )
    return voyage


def get_execution_service(request: Request) -> ExecutionService:
    svc: ExecutionService = request.app.state.execution_service
    return svc


def get_git_service(request: Request) -> GitService:
    svc: GitService = request.app.state.git_service
    return svc


def get_deployment_backend(request: Request) -> DeploymentBackend:
    backend: DeploymentBackend = request.app.state.deployment_backend
    return backend


async def get_dial_router(
    voyage_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _voyage: Voyage = Depends(get_authorized_voyage),
    mushi: DenDenMushi = Depends(get_den_den_mushi),
    redis: Redis = Depends(get_redis),
) -> AsyncGenerator[DialSystemRouter, None]:
    result = await session.execute(select(DialConfig).where(DialConfig.voyage_id == voyage_id))
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dial config not found for this voyage",
        )
    rate_limiter = RateLimiter(redis)
    router = build_router_from_config(config, settings, mushi, rate_limiter)
    try:
        yield router
    finally:
        await router.close()


def get_pipeline_service(
    dial_router: DialSystemRouter = Depends(get_dial_router),
    mushi: DenDenMushi = Depends(get_den_den_mushi),
    session: AsyncSession = Depends(get_db),
    execution_service: ExecutionService = Depends(get_execution_service),
    git_service: GitService = Depends(get_git_service),
    deployment_backend: DeploymentBackend = Depends(get_deployment_backend),
) -> PipelineService:
    return PipelineService(
        session=session,
        mushi=mushi,
        dial_router=dial_router,
        execution_service=execution_service,
        git_service=git_service,
        deployment_backend=deployment_backend,
    )


async def get_pipeline_service_reader(
    session: AsyncSession = Depends(get_db),
) -> PipelineService:
    return PipelineService.reader(session)
