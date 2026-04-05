from __future__ import annotations

import uuid

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    JWTError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User


class AuthError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code


async def register(
    session: AsyncSession,
    redis: Redis,
    *,
    email: str,
    username: str,
    password: str,
) -> tuple[User, str, str]:
    existing = await session.execute(
        select(User).where((User.email == email) | (User.username == username))
    )
    if existing.scalar_one_or_none() is not None:
        raise AuthError("USER_EXISTS", "A user with that email or username already exists", 409)

    user = User(
        email=email,
        username=username,
        hashed_password=hash_password(password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    await _store_refresh_token(redis, refresh, user.id)
    return user, access, refresh


async def login(
    session: AsyncSession,
    redis: Redis,
    *,
    email: str,
    password: str,
) -> tuple[User, str, str]:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        raise AuthError("INVALID_CREDENTIALS", "Incorrect email or password", 401)
    if not user.is_active:
        raise AuthError("USER_INACTIVE", "This account has been deactivated", 403)

    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    await _store_refresh_token(redis, refresh, user.id)
    return user, access, refresh


async def refresh_tokens(
    session: AsyncSession,
    redis: Redis,
    *,
    refresh_token: str,
) -> tuple[str, str]:
    try:
        payload = decode_token(refresh_token)
    except JWTError as exc:
        raise AuthError("INVALID_TOKEN", "Invalid or expired refresh token", 401) from exc

    if payload.get("type") != "refresh":
        raise AuthError("INVALID_TOKEN", "Token is not a refresh token", 401)

    jti = payload.get("jti", "")
    stored = await redis.get(f"refresh:{jti}")
    if stored is None:
        raise AuthError("TOKEN_REVOKED", "Refresh token has been revoked", 401)

    # Revoke old token
    await redis.delete(f"refresh:{jti}")

    user_id = uuid.UUID(payload["sub"])
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthError("USER_NOT_FOUND", "User no longer exists or is inactive", 401)

    access = create_access_token(user_id)
    new_refresh = create_refresh_token(user_id)
    await _store_refresh_token(redis, new_refresh, user_id)
    return access, new_refresh


async def _store_refresh_token(
    redis: Redis,
    token: str,
    user_id: uuid.UUID,
) -> None:
    payload = decode_token(token)
    jti = payload["jti"]
    ttl = settings.refresh_token_expire_minutes * 60
    await redis.setex(f"refresh:{jti}", ttl, str(user_id))
