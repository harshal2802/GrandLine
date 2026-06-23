"""Tests for ClaudeAuthService (mocked Cabin run + mocked session — no DB, no CLI).

Phase C0: the device-login is run INSIDE the user's Cabin; on success the captured
CLAUDE_CODE_OAUTH_TOKEN is vaulted in the Sea Chest (kind="claude_code"). The token
is NEVER returned or logged — ClaudeLoginStatus carries status + label only.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.claude_auth_service as cas
from app.cabin.backend import CabinRunResult
from app.services.claude_auth_service import ClaudeAuthError, ClaudeAuthService

USER_ID = uuid.uuid4()
OTHER_USER_ID = uuid.uuid4()


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        claude_code_login_command="claude setup-token",
        # Sea Chest crypto settings consumed when poll stores the token.
        seachest_key="test-vault-key",
        debug=False,
    )


def _run_result(stdout: str = "", stderr: str = "") -> CabinRunResult:
    return CabinRunResult(
        cabin_id="cabin-1",
        exit_code=0,
        stdout=stdout,
        stderr=stderr,
        timed_out=False,
        duration_seconds=0.1,
    )


def _cabin(*results: CabinRunResult) -> MagicMock:
    cabin = MagicMock()
    cabin.run = AsyncMock(side_effect=list(results))
    return cabin


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    cas._LOGINS.clear()


class TestStartLogin:
    @pytest.mark.asyncio
    async def test_parses_verification_uri_from_cabin_output(self) -> None:
        cabin = _cabin(
            _run_result(
                stdout=(
                    "Visit https://claude.ai/oauth/device?code=WXYZ to authenticate.\n"
                    "Enter code: WXYZ-1234\n"
                )
            )
        )
        svc = ClaudeAuthService(AsyncMock(), _settings(), cabin_service=cabin)

        start = await svc.start_login(USER_ID)

        assert start.verification_uri == "https://claude.ai/oauth/device?code=WXYZ"
        assert start.user_code == "WXYZ-1234"
        assert start.login_id  # opaque handle
        # The login command was run in the user's Cabin.
        cabin.run.assert_awaited_once()
        assert cabin.run.call_args.args[0] == USER_ID

    @pytest.mark.asyncio
    async def test_no_verification_uri_raises_login_failed(self) -> None:
        cabin = _cabin(_run_result(stdout="nothing useful here"))
        svc = ClaudeAuthService(AsyncMock(), _settings(), cabin_service=cabin)

        with pytest.raises(ClaudeAuthError) as exc:
            await svc.start_login(USER_ID)
        assert exc.value.code == "LOGIN_FAILED"

    @pytest.mark.asyncio
    async def test_no_cabin_runner_raises_cabin_unavailable(self) -> None:
        svc = ClaudeAuthService(AsyncMock(), _settings(), cabin_service=None)
        with pytest.raises(ClaudeAuthError) as exc:
            await svc.start_login(USER_ID)
        assert exc.value.code == "CABIN_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_start_does_not_leak_token_in_result(self) -> None:
        # Even if the start run already prints the token, it never appears outbound.
        cabin = _cabin(
            _run_result(
                stdout=(
                    "Visit https://claude.ai/device to approve.\n"
                    "Token: sk-ant-oat01-supersecret\n"
                )
            )
        )
        svc = ClaudeAuthService(AsyncMock(), _settings(), cabin_service=cabin)
        start = await svc.start_login(USER_ID)
        assert "sk-ant-oat01-supersecret" not in start.model_dump_json()


class TestPollLogin:
    @pytest.mark.asyncio
    async def test_pending_until_token_captured(self) -> None:
        # Start run prints only the URL; the follow-up poll run still has no token.
        start_run = _run_result(stdout="Visit https://claude.ai/device to approve.")
        poll_run = _run_result(stdout="Waiting for approval…")
        cabin = _cabin(start_run, poll_run)
        svc = ClaudeAuthService(AsyncMock(), _settings(), cabin_service=cabin)

        start = await svc.start_login(USER_ID)
        status = await svc.poll_login(USER_ID, start.login_id)

        assert status.status == "pending"
        assert status.label is None

    @pytest.mark.asyncio
    async def test_connected_stores_token_in_sea_chest(self) -> None:
        # Start has no token; the poll re-run surfaces it post-approval.
        start_run = _run_result(stdout="Visit https://claude.ai/device to approve.")
        poll_run = _run_result(stdout="Success! Token: sk-ant-oat01-realtoken")
        cabin = _cabin(start_run, poll_run)
        session = AsyncMock()
        svc = ClaudeAuthService(session, _settings(), cabin_service=cabin)

        start = await svc.start_login(USER_ID)
        store = AsyncMock()
        with patch.object(cas, "SeaChestService") as sea_cls:
            sea_cls.return_value.store = store
            status = await svc.poll_login(USER_ID, start.login_id)

        assert status.status == "connected"
        assert status.label == "claude-login"
        store.assert_awaited_once()
        args, kwargs = store.call_args.args, store.call_args.kwargs
        assert args[0] == USER_ID
        assert args[1] == "claude_code"
        assert args[2] == "sk-ant-oat01-realtoken"
        assert kwargs["label"] == "claude-login"

    @pytest.mark.asyncio
    async def test_connected_when_start_already_captured_token(self) -> None:
        # If the start run already captured the token, poll stores it with no re-run.
        start_run = _run_result(
            stdout="Visit https://claude.ai/device\nToken: sk-ant-oat01-fromstart"
        )
        cabin = _cabin(start_run)  # only one run is provided — poll must not re-run
        svc = ClaudeAuthService(AsyncMock(), _settings(), cabin_service=cabin)

        start = await svc.start_login(USER_ID)
        store = AsyncMock()
        with patch.object(cas, "SeaChestService") as sea_cls:
            sea_cls.return_value.store = store
            status = await svc.poll_login(USER_ID, start.login_id)

        assert status.status == "connected"
        store.assert_awaited_once()
        assert store.call_args.args[2] == "sk-ant-oat01-fromstart"
        # poll did not need a second Cabin run.
        assert cabin.run.await_count == 1

    @pytest.mark.asyncio
    async def test_token_never_in_status(self) -> None:
        start_run = _run_result(stdout="Visit https://claude.ai/device")
        poll_run = _run_result(stdout="Token: sk-ant-oat01-secret")
        cabin = _cabin(start_run, poll_run)
        svc = ClaudeAuthService(AsyncMock(), _settings(), cabin_service=cabin)

        start = await svc.start_login(USER_ID)
        with patch.object(cas, "SeaChestService") as sea_cls:
            sea_cls.return_value.store = AsyncMock()
            status = await svc.poll_login(USER_ID, start.login_id)

        assert "sk-ant-oat01-secret" not in status.model_dump_json()

    @pytest.mark.asyncio
    async def test_unknown_login_id_returns_error(self) -> None:
        svc = ClaudeAuthService(AsyncMock(), _settings(), cabin_service=_cabin())
        status = await svc.poll_login(USER_ID, "does-not-exist")
        assert status.status == "error"
        assert status.error == "unknown_login"

    @pytest.mark.asyncio
    async def test_poll_is_owner_scoped(self) -> None:
        # A login started by USER_ID cannot be polled by another user.
        start_run = _run_result(stdout="Visit https://claude.ai/device")
        cabin = _cabin(start_run)
        svc = ClaudeAuthService(AsyncMock(), _settings(), cabin_service=cabin)

        start = await svc.start_login(USER_ID)
        status = await svc.poll_login(OTHER_USER_ID, start.login_id)
        assert status.status == "error"
        assert status.error == "unknown_login"
