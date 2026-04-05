"""Tests for auth endpoints, security helpers, and default-deny middleware."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from jose import jwt

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair

# ---- Password hashing tests ----


class TestPasswordHashing:
    def test_hash_password_returns_bcrypt_hash(self) -> None:
        hashed = hash_password("test-password")
        assert hashed != "test-password"
        assert hashed.startswith("$2b$")

    def test_verify_password_correct(self) -> None:
        hashed = hash_password("correct-password")
        assert verify_password("correct-password", hashed) is True

    def test_verify_password_incorrect(self) -> None:
        hashed = hash_password("correct-password")
        assert verify_password("wrong-password", hashed) is False


# ---- JWT token tests ----


class TestJWTTokens:
    def test_create_access_token_contains_correct_claims(self) -> None:
        user_id = uuid.uuid4()
        token = create_access_token(user_id)
        payload = decode_token(token)

        assert payload["sub"] == str(user_id)
        assert payload["type"] == "access"
        assert "exp" in payload

    def test_create_refresh_token_contains_correct_claims(self) -> None:
        user_id = uuid.uuid4()
        token = create_refresh_token(user_id)
        payload = decode_token(token)

        assert payload["sub"] == str(user_id)
        assert payload["type"] == "refresh"
        assert "jti" in payload
        assert "exp" in payload

    def test_access_token_expires_at_configured_time(self) -> None:
        user_id = uuid.uuid4()
        before = datetime.now(UTC)
        token = create_access_token(user_id)
        payload = decode_token(token)

        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        expected = before + timedelta(minutes=settings.access_token_expire_minutes)
        # Allow 5 seconds of tolerance
        assert abs((exp - expected).total_seconds()) < 5

    def test_refresh_token_has_unique_jti(self) -> None:
        user_id = uuid.uuid4()
        t1 = create_refresh_token(user_id)
        t2 = create_refresh_token(user_id)
        p1 = decode_token(t1)
        p2 = decode_token(t2)
        assert p1["jti"] != p2["jti"]

    def test_decode_expired_token_raises(self) -> None:
        payload: dict[str, Any] = {
            "sub": str(uuid.uuid4()),
            "exp": datetime.now(UTC) - timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

        with pytest.raises(Exception):  # JWTError — ExpiredSignatureError
            decode_token(token)

    def test_decode_invalid_token_raises(self) -> None:
        with pytest.raises(Exception):
            decode_token("not-a-real-token")

    def test_decode_wrong_secret_raises(self) -> None:
        payload: dict[str, Any] = {
            "sub": str(uuid.uuid4()),
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
        with pytest.raises(Exception):
            decode_token(token)


# ---- Schema validation tests ----


class TestAuthSchemas:
    def test_register_request_valid(self) -> None:
        req = RegisterRequest(email="luffy@grandline.dev", username="luffy", password="gear5")
        assert req.email == "luffy@grandline.dev"
        assert req.username == "luffy"

    def test_register_request_invalid_email(self) -> None:
        with pytest.raises(Exception):
            RegisterRequest(email="not-an-email", username="luffy", password="gear5")

    def test_login_request_valid(self) -> None:
        req = LoginRequest(email="luffy@grandline.dev", password="gear5")
        assert req.email == "luffy@grandline.dev"

    def test_refresh_request_valid(self) -> None:
        req = RefreshRequest(refresh_token="some.jwt.token")
        assert req.refresh_token == "some.jwt.token"

    def test_token_pair_defaults(self) -> None:
        tp = TokenPair(access_token="a", refresh_token="r")
        assert tp.token_type == "bearer"


# ---- Default-deny middleware tests ----


class TestDefaultDenyMiddleware:
    def test_public_paths_are_defined(self) -> None:
        from app.core.middleware import PUBLIC_PATHS

        assert "/api/v1/health" in PUBLIC_PATHS
        assert "/api/v1/auth/register" in PUBLIC_PATHS
        assert "/api/v1/auth/login" in PUBLIC_PATHS
        assert "/api/v1/auth/refresh" in PUBLIC_PATHS

    @pytest.mark.asyncio
    async def test_middleware_allows_public_path(self) -> None:
        from app.core.middleware import DefaultDenyMiddleware

        request = MagicMock()
        request.url.path = "/api/v1/health"
        request.method = "GET"

        expected_response = MagicMock()
        call_next = AsyncMock(return_value=expected_response)

        middleware = DefaultDenyMiddleware(app=MagicMock())
        response = await middleware.dispatch(request, call_next)
        assert response is expected_response

    @pytest.mark.asyncio
    async def test_middleware_blocks_unauthenticated_api_request(self) -> None:
        from app.core.middleware import DefaultDenyMiddleware

        request = MagicMock()
        request.url.path = "/api/v1/voyages"
        request.method = "GET"
        request.headers = {}

        call_next = AsyncMock()

        middleware = DefaultDenyMiddleware(app=MagicMock())
        response = await middleware.dispatch(request, call_next)
        assert response.status_code == 401
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_middleware_passes_authenticated_request(self) -> None:
        from app.core.middleware import DefaultDenyMiddleware

        request = MagicMock()
        request.url.path = "/api/v1/voyages"
        request.method = "GET"
        request.headers = {"authorization": "Bearer some-valid-token"}

        expected_response = MagicMock()
        call_next = AsyncMock(return_value=expected_response)

        middleware = DefaultDenyMiddleware(app=MagicMock())
        response = await middleware.dispatch(request, call_next)
        assert response is expected_response

    @pytest.mark.asyncio
    async def test_middleware_allows_options_preflight(self) -> None:
        from app.core.middleware import DefaultDenyMiddleware

        request = MagicMock()
        request.url.path = "/api/v1/voyages"
        request.method = "OPTIONS"

        expected_response = MagicMock()
        call_next = AsyncMock(return_value=expected_response)

        middleware = DefaultDenyMiddleware(app=MagicMock())
        response = await middleware.dispatch(request, call_next)
        assert response is expected_response

    @pytest.mark.asyncio
    async def test_middleware_ignores_non_api_paths(self) -> None:
        from app.core.middleware import DefaultDenyMiddleware

        request = MagicMock()
        request.url.path = "/some-page"
        request.method = "GET"

        expected_response = MagicMock()
        call_next = AsyncMock(return_value=expected_response)

        middleware = DefaultDenyMiddleware(app=MagicMock())
        response = await middleware.dispatch(request, call_next)
        assert response is expected_response


# ---- Auth service tests (mocked DB + Redis) ----


class TestAuthService:
    @pytest.mark.asyncio
    async def test_register_creates_user_and_returns_tokens(self) -> None:
        from app.services.auth_service import register

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        mock_redis = AsyncMock()

        user, access, refresh = await register(
            mock_session,
            mock_redis,
            email="luffy@grandline.dev",
            username="luffy",
            password="gear5",
        )

        assert user.email == "luffy@grandline.dev"
        assert user.username == "luffy"
        assert access  # non-empty string
        assert refresh  # non-empty string
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        mock_redis.setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_register_rejects_duplicate_user(self) -> None:
        from app.services.auth_service import AuthError, register

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()  # existing user
        mock_session.execute.return_value = mock_result

        mock_redis = AsyncMock()

        with pytest.raises(AuthError) as exc_info:
            await register(
                mock_session,
                mock_redis,
                email="taken@grandline.dev",
                username="taken",
                password="gear5",
            )
        assert exc_info.value.code == "USER_EXISTS"
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_login_returns_tokens_for_valid_credentials(self) -> None:
        from app.services.auth_service import login

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.hashed_password = hash_password("gear5")
        mock_user.is_active = True

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        mock_redis = AsyncMock()

        user, access, refresh = await login(
            mock_session, mock_redis, email="luffy@grandline.dev", password="gear5"
        )
        assert user is mock_user
        assert access
        assert refresh

    @pytest.mark.asyncio
    async def test_login_rejects_wrong_password(self) -> None:
        from app.services.auth_service import AuthError, login

        mock_user = MagicMock()
        mock_user.hashed_password = hash_password("gear5")
        mock_user.is_active = True

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        mock_redis = AsyncMock()

        with pytest.raises(AuthError) as exc_info:
            await login(mock_session, mock_redis, email="luffy@grandline.dev", password="wrong")
        assert exc_info.value.code == "INVALID_CREDENTIALS"

    @pytest.mark.asyncio
    async def test_login_rejects_nonexistent_user(self) -> None:
        from app.services.auth_service import AuthError, login

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        mock_redis = AsyncMock()

        with pytest.raises(AuthError) as exc_info:
            await login(mock_session, mock_redis, email="nope@grandline.dev", password="gear5")
        assert exc_info.value.code == "INVALID_CREDENTIALS"

    @pytest.mark.asyncio
    async def test_login_rejects_inactive_user(self) -> None:
        from app.services.auth_service import AuthError, login

        mock_user = MagicMock()
        mock_user.hashed_password = hash_password("gear5")
        mock_user.is_active = False

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        mock_redis = AsyncMock()

        with pytest.raises(AuthError) as exc_info:
            await login(mock_session, mock_redis, email="luffy@grandline.dev", password="gear5")
        assert exc_info.value.code == "USER_INACTIVE"

    @pytest.mark.asyncio
    async def test_refresh_rotates_tokens(self) -> None:
        from app.services.auth_service import refresh_tokens

        user_id = uuid.uuid4()
        old_refresh = create_refresh_token(user_id)
        old_payload = decode_token(old_refresh)
        old_jti = old_payload["jti"]

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.is_active = True

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        mock_redis = AsyncMock()
        mock_redis.get.return_value = str(user_id)  # token exists in Redis

        access, new_refresh = await refresh_tokens(
            mock_session, mock_redis, refresh_token=old_refresh
        )

        assert access
        assert new_refresh
        assert new_refresh != old_refresh
        mock_redis.delete.assert_awaited_once_with(f"refresh:{old_jti}")

    @pytest.mark.asyncio
    async def test_refresh_rejects_revoked_token(self) -> None:
        from app.services.auth_service import AuthError, refresh_tokens

        user_id = uuid.uuid4()
        old_refresh = create_refresh_token(user_id)

        mock_session = AsyncMock()
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # token not in Redis = revoked

        with pytest.raises(AuthError) as exc_info:
            await refresh_tokens(mock_session, mock_redis, refresh_token=old_refresh)
        assert exc_info.value.code == "TOKEN_REVOKED"

    @pytest.mark.asyncio
    async def test_refresh_rejects_access_token(self) -> None:
        from app.services.auth_service import AuthError, refresh_tokens

        user_id = uuid.uuid4()
        access = create_access_token(user_id)  # wrong type

        mock_session = AsyncMock()
        mock_redis = AsyncMock()

        with pytest.raises(AuthError) as exc_info:
            await refresh_tokens(mock_session, mock_redis, refresh_token=access)
        assert exc_info.value.code == "INVALID_TOKEN"
