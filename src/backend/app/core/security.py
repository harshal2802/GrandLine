from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# ---- password helpers ----


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ---- JWT helpers ----


def create_access_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "exp": expire,
        "type": "access",
    }
    token: str = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token


def create_refresh_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.refresh_token_expire_minutes)
    jti = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
        "jti": jti,
    }
    token: str = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises JWTError on failure."""
    result: dict[str, Any] = jwt.decode(
        token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
    )
    return result


__all__ = [
    "JWTError",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_password",
    "verify_password",
]
