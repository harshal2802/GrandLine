"""Tests for GithubAuthService (mocked httpx + AsyncSession — no DB, no network)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.github_auth_service import GithubAuthError, GithubAuthService

USER_ID = uuid.uuid4()


def _settings(
    client_id: str = "Iv1.client123",
    api_base: str = "https://api.github.com",
) -> SimpleNamespace:
    return SimpleNamespace(
        github_oauth_client_id=client_id,
        github_api_base_url=api_base,
        # Sea Chest crypto settings consumed when poll stores the token.
        seachest_key="test-vault-key",
        debug=False,
    )


def _json_response(payload: dict, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


def _mock_async_client(responses: list[MagicMock]) -> tuple[MagicMock, list[MagicMock]]:
    """Wire an AsyncClient factory whose post/get return queued responses in order."""
    calls: list[MagicMock] = []

    async def _post(*args: object, **kwargs: object) -> MagicMock:
        resp = responses[len(calls)]
        call = MagicMock(args=args, kwargs=kwargs)
        calls.append(call)
        return resp

    async def _get(*args: object, **kwargs: object) -> MagicMock:
        resp = responses[len(calls)]
        call = MagicMock(args=args, kwargs=kwargs)
        calls.append(call)
        return resp

    client = MagicMock()
    client.post = AsyncMock(side_effect=_post)
    client.get = AsyncMock(side_effect=_get)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    factory = MagicMock(return_value=client)
    return factory, calls


class TestStartDeviceFlow:
    @pytest.mark.asyncio
    async def test_builds_request_and_parses_codes(self) -> None:
        svc = GithubAuthService(AsyncMock(), _settings(client_id="Iv1.abc"))
        factory, calls = _mock_async_client(
            [
                _json_response(
                    {
                        "device_code": "dev-code-xyz",
                        "user_code": "ABCD-1234",
                        "verification_uri": "https://github.com/login/device",
                        "interval": 5,
                        "expires_in": 899,
                    }
                )
            ]
        )
        with patch("app.services.github_auth_service.httpx.AsyncClient", factory):
            start = await svc.start_device_flow()

        # Request: fixed github.com host, client_id + scope=repo, JSON accept.
        call = calls[0]
        assert call.args[0] == "https://github.com/login/device/code"
        assert call.kwargs["data"]["client_id"] == "Iv1.abc"
        assert call.kwargs["data"]["scope"] == "repo"
        assert call.kwargs["headers"]["Accept"] == "application/json"
        # Parsed result.
        assert start.user_code == "ABCD-1234"
        assert start.verification_uri == "https://github.com/login/device"
        assert start.device_code == "dev-code-xyz"
        assert start.interval == 5
        assert start.expires_in == 899

    @pytest.mark.asyncio
    async def test_missing_client_id_raises(self) -> None:
        svc = GithubAuthService(AsyncMock(), _settings(client_id=""))
        with pytest.raises(GithubAuthError) as exc:
            await svc.start_device_flow()
        assert exc.value.code == "OAUTH_NOT_CONFIGURED"

    @pytest.mark.asyncio
    async def test_non_200_raises(self) -> None:
        svc = GithubAuthService(AsyncMock(), _settings())
        factory, _calls = _mock_async_client([_json_response({}, status_code=500)])
        with patch("app.services.github_auth_service.httpx.AsyncClient", factory):
            with pytest.raises(GithubAuthError) as exc:
                await svc.start_device_flow()
        assert exc.value.code == "DEVICE_FLOW_FAILED"


class TestPollDeviceFlow:
    @pytest.mark.asyncio
    async def test_pending_when_authorization_pending(self) -> None:
        svc = GithubAuthService(AsyncMock(), _settings())
        factory, _calls = _mock_async_client([_json_response({"error": "authorization_pending"})])
        with patch("app.services.github_auth_service.httpx.AsyncClient", factory):
            status = await svc.poll_device_flow(USER_ID, "dev-code")
        assert status.status == "pending"
        assert status.login is None

    @pytest.mark.asyncio
    async def test_pending_when_slow_down(self) -> None:
        svc = GithubAuthService(AsyncMock(), _settings())
        factory, _calls = _mock_async_client([_json_response({"error": "slow_down"})])
        with patch("app.services.github_auth_service.httpx.AsyncClient", factory):
            status = await svc.poll_device_flow(USER_ID, "dev-code")
        assert status.status == "pending"

    @pytest.mark.asyncio
    async def test_connected_fetches_login_and_stores_token(self) -> None:
        session = AsyncMock()
        svc = GithubAuthService(session, _settings())
        # Two HTTP calls: access_token POST, then /user GET.
        factory, calls = _mock_async_client(
            [
                _json_response({"access_token": "gho_secret_token", "token_type": "bearer"}),
                _json_response({"login": "monkey-d-luffy"}),
            ]
        )
        store = AsyncMock()
        with (
            patch("app.services.github_auth_service.httpx.AsyncClient", factory),
            patch("app.services.github_auth_service.SeaChestService") as sea_cls,
        ):
            sea_cls.return_value.store = store
            status = await svc.poll_device_flow(USER_ID, "dev-code")

        assert status.status == "connected"
        assert status.login == "monkey-d-luffy"
        # The token was stored in the Sea Chest under @login — never returned.
        store.assert_awaited_once()
        args, kwargs = store.call_args.args, store.call_args.kwargs
        assert args[0] == USER_ID
        assert args[1] == "github"
        assert args[2] == "gho_secret_token"
        assert kwargs["label"] == "@monkey-d-luffy"
        # The grant_type + device_code went to the access_token endpoint on github.com.
        token_call = calls[0]
        assert token_call.args[0] == "https://github.com/login/oauth/access_token"
        assert token_call.kwargs["data"]["device_code"] == "dev-code"
        assert (
            token_call.kwargs["data"]["grant_type"]
            == "urn:ietf:params:oauth:grant-type:device_code"
        )
        # The /user lookup used the fixed api_base + Bearer of the new token.
        user_call = calls[1]
        assert user_call.args[0] == "https://api.github.com/user"
        assert user_call.kwargs["headers"]["Authorization"] == "Bearer gho_secret_token"

    @pytest.mark.asyncio
    async def test_token_never_in_status(self) -> None:
        session = AsyncMock()
        svc = GithubAuthService(session, _settings())
        factory, _calls = _mock_async_client(
            [
                _json_response({"access_token": "gho_secret_token"}),
                _json_response({"login": "zoro"}),
            ]
        )
        with (
            patch("app.services.github_auth_service.httpx.AsyncClient", factory),
            patch("app.services.github_auth_service.SeaChestService") as sea_cls,
        ):
            sea_cls.return_value.store = AsyncMock()
            status = await svc.poll_device_flow(USER_ID, "dev-code")
        # No field of the outbound status carries the token.
        assert "gho_secret_token" not in status.model_dump_json()

    @pytest.mark.asyncio
    async def test_expired_token_returns_error(self) -> None:
        svc = GithubAuthService(AsyncMock(), _settings())
        factory, _calls = _mock_async_client([_json_response({"error": "expired_token"})])
        store = AsyncMock()
        with (
            patch("app.services.github_auth_service.httpx.AsyncClient", factory),
            patch("app.services.github_auth_service.SeaChestService") as sea_cls,
        ):
            sea_cls.return_value.store = store
            status = await svc.poll_device_flow(USER_ID, "dev-code")
        assert status.status == "error"
        assert status.error == "expired_token"
        store.assert_not_called()

    @pytest.mark.asyncio
    async def test_access_denied_returns_error(self) -> None:
        svc = GithubAuthService(AsyncMock(), _settings())
        factory, _calls = _mock_async_client([_json_response({"error": "access_denied"})])
        with patch("app.services.github_auth_service.httpx.AsyncClient", factory):
            status = await svc.poll_device_flow(USER_ID, "dev-code")
        assert status.status == "error"
        assert status.error == "access_denied"

    @pytest.mark.asyncio
    async def test_missing_client_id_raises(self) -> None:
        svc = GithubAuthService(AsyncMock(), _settings(client_id=""))
        with pytest.raises(GithubAuthError) as exc:
            await svc.poll_device_flow(USER_ID, "dev-code")
        assert exc.value.code == "OAUTH_NOT_CONFIGURED"
