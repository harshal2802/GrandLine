from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, get_redis
from app.models import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair
from app.schemas.user import UserRead
from app.services.auth_service import AuthError, login, refresh_tokens, register

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenPair, status_code=201)
async def register_user(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TokenPair:
    try:
        _user, access, refresh = await register(
            session,
            redis,
            email=body.email,
            username=body.username,
            password=body.password,
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenPair)
async def login_user(
    body: LoginRequest,
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TokenPair:
    try:
        _user, access, refresh = await login(
            session,
            redis,
            email=body.email,
            password=body.password,
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    body: RefreshRequest,
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TokenPair:
    try:
        access, new_refresh = await refresh_tokens(
            session,
            redis,
            refresh_token=body.refresh_token,
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc
    return TokenPair(access_token=access, refresh_token=new_refresh)


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
