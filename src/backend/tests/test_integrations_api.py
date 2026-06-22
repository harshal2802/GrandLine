"""Tests for the integrations REST API (direct endpoint calls) — Phase A3.

Default-deny + owner-scoped + NO token in any response.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.schemas.integrations import (
    DeviceFlowPollRequest,
    DeviceFlowStart,
    DeviceFlowStatus,
)
from app.services.github_auth_service import GithubAuthError

USER_ID = uuid.uuid4()
OTHER_USER_ID = uuid.uuid4()


def _user(user_id: uuid.UUID = USER_ID) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    return user


class TestStartEndpoint:
    @pytest.mark.asyncio
    async def test_start_returns_codes_no_token(self) -> None:
        from app.api.v1.integrations import start_github_device_flow

        svc = AsyncMock()
        svc.start_device_flow = AsyncMock(
            return_value=DeviceFlowStart(
                user_code="ABCD-1234",
                verification_uri="https://github.com/login/device",
                device_code="dev-code-xyz",
                interval=5,
                expires_in=900,
            )
        )

        result = await start_github_device_flow(_user(), svc)

        assert result.user_code == "ABCD-1234"
        assert result.verification_uri == "https://github.com/login/device"
        # A device flow start carries no access token field at all.
        assert "access_token" not in result.model_dump()

    @pytest.mark.asyncio
    async def test_start_unconfigured_503(self) -> None:
        from app.api.v1.integrations import start_github_device_flow

        svc = AsyncMock()
        svc.start_device_flow = AsyncMock(
            side_effect=GithubAuthError("OAUTH_NOT_CONFIGURED", "nope")
        )

        with pytest.raises(HTTPException) as exc:
            await start_github_device_flow(_user(), svc)
        assert exc.value.status_code == 503


class TestPollEndpoint:
    @pytest.mark.asyncio
    async def test_poll_owner_scoped_and_returns_login_no_token(self) -> None:
        from app.api.v1.integrations import poll_github_device_flow

        svc = AsyncMock()
        svc.poll_device_flow = AsyncMock(
            return_value=DeviceFlowStatus(status="connected", login="luffy")
        )
        body = DeviceFlowPollRequest(device_code="dev-code-xyz")

        result = await poll_github_device_flow(body, _user(), svc)

        assert result.status == "connected"
        assert result.login == "luffy"
        # The poll passes the AUTHENTICATED user's id (owner-scoped).
        svc.poll_device_flow.assert_awaited_once_with(USER_ID, "dev-code-xyz")
        # No token anywhere in the response.
        assert "access_token" not in result.model_dump()

    @pytest.mark.asyncio
    async def test_poll_pending(self) -> None:
        from app.api.v1.integrations import poll_github_device_flow

        svc = AsyncMock()
        svc.poll_device_flow = AsyncMock(return_value=DeviceFlowStatus(status="pending"))
        body = DeviceFlowPollRequest(device_code="dev-code-xyz")

        result = await poll_github_device_flow(body, _user(), svc)
        assert result.status == "pending"
        assert result.login is None

    @pytest.mark.asyncio
    async def test_poll_uses_caller_id_not_foreign(self) -> None:
        from app.api.v1.integrations import poll_github_device_flow

        svc = AsyncMock()
        svc.poll_device_flow = AsyncMock(
            return_value=DeviceFlowStatus(status="connected", login="zoro")
        )
        body = DeviceFlowPollRequest(device_code="dc")

        await poll_github_device_flow(body, _user(OTHER_USER_ID), svc)
        svc.poll_device_flow.assert_awaited_once_with(OTHER_USER_ID, "dc")
