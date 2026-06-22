"""Tests for the Message-in-a-Bottle webhook API (direct endpoint calls)."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.trigger_service import TriggerError, TriggerService, verify_github_signature

SECRET = "s3cr3t-bottle"
VOYAGE_ID = uuid.uuid4()

BODY = (
    b'{"action":"opened",'
    b'"issue":{"number":42,"title":"Login broken",'
    b'"body":"repro","html_url":"https://github.com/acme/widgets/issues/42",'
    b'"labels":[{"name":"grandline"}]},'
    b'"repository":{"full_name":"acme/widgets","clone_url":"https://github.com/acme/widgets.git"},'
    b'"sender":{"login":"reporter"}}'
)

NON_TRIGGER_BODY = (
    b'{"action":"closed",'
    b'"issue":{"number":42,"title":"Login broken",'
    b'"html_url":"https://github.com/acme/widgets/issues/42","labels":[]},'
    b'"repository":{"full_name":"acme/widgets"},'
    b'"sender":{"login":"reporter"}}'
)


def _sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _request(body: bytes, signature: str | None) -> MagicMock:
    request = MagicMock()
    request.body = AsyncMock(return_value=body)
    headers = {} if signature is None else {"X-Hub-Signature-256": signature}
    request.headers = headers
    return request


def _response() -> MagicMock:
    return MagicMock()


def _real_service() -> TriggerService:
    """A service whose static/sync verification + gating are real, DB methods mocked."""
    service = TriggerService(AsyncMock())
    service.resolve_trigger_user = AsyncMock()
    service.ingest_github_issue = AsyncMock()
    return service


class TestSignatureGate:
    @pytest.mark.asyncio
    async def test_bad_signature_returns_401(self) -> None:
        from app.api.v1.triggers import github_trigger

        service = _real_service()
        request = _request(BODY, "sha256=deadbeef")
        with patch("app.api.v1.triggers.settings.github_webhook_secret", SECRET):
            with pytest.raises(HTTPException) as exc:
                await github_trigger(request, _response(), service)
        assert exc.value.status_code == 401
        assert exc.value.detail["error"]["code"] == "INVALID_SIGNATURE"
        service.ingest_github_issue.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_signature_returns_401(self) -> None:
        from app.api.v1.triggers import github_trigger

        service = _real_service()
        request = _request(BODY, None)
        with patch("app.api.v1.triggers.settings.github_webhook_secret", SECRET):
            with pytest.raises(HTTPException) as exc:
                await github_trigger(request, _response(), service)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_unconfigured_secret_returns_401(self) -> None:
        from app.api.v1.triggers import github_trigger

        service = _real_service()
        request = _request(BODY, _sign(BODY, SECRET))
        with patch("app.api.v1.triggers.settings.github_webhook_secret", None):
            with pytest.raises(HTTPException) as exc:
                await github_trigger(request, _response(), service)
        assert exc.value.status_code == 401


class TestIgnored:
    @pytest.mark.asyncio
    async def test_non_trigger_event_returns_200_ignored(self) -> None:
        from app.api.v1.triggers import github_trigger

        service = _real_service()
        request = _request(NON_TRIGGER_BODY, _sign(NON_TRIGGER_BODY, SECRET))
        response = _response()
        with (
            patch("app.api.v1.triggers.settings.github_webhook_secret", SECRET),
            patch("app.services.trigger_service.settings.trigger_label", "grandline"),
        ):
            result = await github_trigger(request, response, service)

        assert result.status == "ignored"
        assert result.voyage_id is None
        service.ingest_github_issue.assert_not_called()


class TestCharted:
    @pytest.mark.asyncio
    async def test_valid_signed_issue_returns_201_charted(self) -> None:
        from app.api.v1.triggers import github_trigger

        user = MagicMock()
        voyage = MagicMock()
        voyage.id = VOYAGE_ID

        service = _real_service()
        service.resolve_trigger_user = AsyncMock(return_value=user)
        service.ingest_github_issue = AsyncMock(return_value=voyage)

        request = _request(BODY, _sign(BODY, SECRET))
        response = _response()
        with (
            patch("app.api.v1.triggers.settings.github_webhook_secret", SECRET),
            patch("app.services.trigger_service.settings.trigger_label", "grandline"),
        ):
            result = await github_trigger(request, response, service)

        assert result.status == "charted"
        assert result.voyage_id == VOYAGE_ID
        assert response.status_code == 201
        service.ingest_github_issue.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unconfigured_user_returns_422(self) -> None:
        from app.api.v1.triggers import github_trigger

        service = _real_service()
        service.resolve_trigger_user = AsyncMock(
            side_effect=TriggerError("TRIGGER_USER_UNCONFIGURED", "nope")
        )

        request = _request(BODY, _sign(BODY, SECRET))
        with (
            patch("app.api.v1.triggers.settings.github_webhook_secret", SECRET),
            patch("app.services.trigger_service.settings.trigger_label", "grandline"),
        ):
            with pytest.raises(HTTPException) as exc:
                await github_trigger(request, _response(), service)
        assert exc.value.status_code == 422
        assert exc.value.detail["error"]["code"] == "TRIGGER_USER_UNCONFIGURED"

    @pytest.mark.asyncio
    async def test_user_not_found_returns_503(self) -> None:
        from app.api.v1.triggers import github_trigger

        service = _real_service()
        service.resolve_trigger_user = AsyncMock(
            side_effect=TriggerError("TRIGGER_USER_NOT_FOUND", "nope")
        )

        request = _request(BODY, _sign(BODY, SECRET))
        with (
            patch("app.api.v1.triggers.settings.github_webhook_secret", SECRET),
            patch("app.services.trigger_service.settings.trigger_label", "grandline"),
        ):
            with pytest.raises(HTTPException) as exc:
                await github_trigger(request, _response(), service)
        assert exc.value.status_code == 503


def test_public_path_allowlisted() -> None:
    from app.core.middleware import PUBLIC_PATHS

    assert "/api/v1/triggers/github" in PUBLIC_PATHS


def test_signature_helper_roundtrip() -> None:
    assert verify_github_signature(BODY, _sign(BODY, SECRET), SECRET) is True
