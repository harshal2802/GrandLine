from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, get_redis
from app.core.config import settings
from app.models import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair
from app.schemas.user import UserRead
from app.services.auth_service import AuthError, login, refresh_tokens, register

router = APIRouter(prefix="/auth", tags=["auth"])

# Cookie name shared between issuance and clearing.
_ACCESS_COOKIE = "access_token"


def _set_access_cookie(response: Response, token: str) -> None:
    """Issue Set-Cookie: access_token=<jwt> alongside the JSON token (Decision 4).

    HttpOnly is intentionally False so frontend JS can read the cookie and
    construct WS handshake URLs (no header-auth on WebSocket). Documented
    trade-off; XSS posture is mitigated separately by CSP.
    """
    response.set_cookie(
        key=_ACCESS_COOKIE,
        value=token,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
        secure=not settings.debug,
        httponly=False,
        samesite="lax",
    )


def _clear_access_cookie(response: Response) -> None:
    response.set_cookie(
        key=_ACCESS_COOKIE,
        value="",
        max_age=0,
        path="/",
        secure=not settings.debug,
        httponly=False,
        samesite="lax",
    )


@router.post("/register", response_model=TokenPair, status_code=201)
async def register_user(
    body: RegisterRequest,
    response: Response,
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
    _set_access_cookie(response, access)
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenPair)
async def login_user(
    body: LoginRequest,
    response: Response,
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
    _set_access_cookie(response, access)
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    body: RefreshRequest,
    response: Response,
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
    _set_access_cookie(response, access)
    return TokenPair(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=200)
async def logout(response: Response) -> dict[str, bool]:
    """Clear the access_token cookie.

    Refresh-token revocation lives in `auth_service.refresh_tokens` (it
    consumes-and-rotates), so logout's contract is just "make the browser
    forget the access cookie".
    """
    _clear_access_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
