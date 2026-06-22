"""Tests for ReturnBottleService (mocked AsyncSession + httpx — no DB, no network)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.return_bottle_service import ReturnBottleService

VOYAGE_ID = uuid.uuid4()


def _settings(token: str = "ghp_test", base: str = "https://api.github.com") -> SimpleNamespace:
    return SimpleNamespace(github_api_token=token, github_api_base_url=base)


def _voyage(
    *,
    title: str = "Fix the flaky login test",
    status: str = "COMPLETED",
    origin: dict | None = None,
    target_repo: str | None = None,
) -> MagicMock:
    v = MagicMock()
    v.id = VOYAGE_ID
    v.title = title
    v.status = status
    v.origin = origin
    v.target_repo = target_repo
    return v


def _github_origin() -> dict:
    return {
        "type": "github_issue",
        "repo": "acme/widgets",
        "issue_number": 42,
        "issue_url": "https://github.com/acme/widgets/issues/42",
        "issue_title": "Login broken",
        "sender": "reporter",
        "received_at": "2026-06-22T00:00:00+00:00",
    }


def _mock_async_client(status_code: int = 201) -> tuple[MagicMock, AsyncMock]:
    """Return (AsyncClient-factory mock, post mock) wired as an async context manager."""
    response = MagicMock()
    response.status_code = status_code
    post = AsyncMock(return_value=response)

    client = MagicMock()
    client.post = post
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    factory = MagicMock(return_value=client)
    return factory, post


class TestBuildSummary:
    def test_includes_title_status_and_duration(self) -> None:
        svc = ReturnBottleService(AsyncMock(), _settings())
        summary = svc.build_summary(
            _voyage(), deployment_url=None, duration_seconds=12.34, phase_count=3
        )
        assert "Fix the flaky login test" in summary
        assert "COMPLETED" in summary
        assert "12.3s" in summary
        assert "Phases charted**: 3" in summary
        # No deploy line when no URL.
        assert "Deployed to" not in summary

    def test_includes_deploy_url_when_present(self) -> None:
        svc = ReturnBottleService(AsyncMock(), _settings())
        summary = svc.build_summary(
            _voyage(),
            deployment_url="https://preview.grandline.dev/abc",
            duration_seconds=1.0,
        )
        assert "https://preview.grandline.dev/abc" in summary
        assert "Deployed to" in summary


class TestPostToGithubIssue:
    @pytest.mark.asyncio
    async def test_builds_correct_url_headers_body_and_returns_true(self) -> None:
        svc = ReturnBottleService(AsyncMock(), _settings(token="ghp_abc"))
        factory, post = _mock_async_client(status_code=201)
        with patch("app.services.return_bottle_service.httpx.AsyncClient", factory):
            ok = await svc.post_to_github_issue(_github_origin(), "hello crew")

        assert ok is True
        post.assert_awaited_once()
        call = post.call_args
        assert call.args[0] == "https://api.github.com/repos/acme/widgets/issues/42/comments"
        assert call.kwargs["headers"]["Authorization"] == "Bearer ghp_abc"
        assert call.kwargs["headers"]["Accept"] == "application/vnd.github+json"
        assert call.kwargs["json"] == {"body": "hello crew"}

    @pytest.mark.asyncio
    async def test_non_2xx_returns_false(self) -> None:
        svc = ReturnBottleService(AsyncMock(), _settings())
        factory, _post = _mock_async_client(status_code=404)
        with patch("app.services.return_bottle_service.httpx.AsyncClient", factory):
            ok = await svc.post_to_github_issue(_github_origin(), "body")
        assert ok is False

    @pytest.mark.asyncio
    async def test_empty_token_skips_and_returns_false(self) -> None:
        svc = ReturnBottleService(AsyncMock(), _settings(token=""))
        factory, post = _mock_async_client()
        with patch("app.services.return_bottle_service.httpx.AsyncClient", factory):
            ok = await svc.post_to_github_issue(_github_origin(), "body")
        assert ok is False
        post.assert_not_called()
        factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_host_is_fixed_not_derived_from_origin(self) -> None:
        # An origin that tries to point the comment at an attacker host must be
        # ignored — only `repo`/`issue_number` are consumed, the host is settings'.
        svc = ReturnBottleService(AsyncMock(), _settings(base="https://api.github.com"))
        factory, post = _mock_async_client(status_code=201)
        evil_origin = {**_github_origin(), "issue_url": "https://evil.example/x"}
        with patch("app.services.return_bottle_service.httpx.AsyncClient", factory):
            await svc.post_to_github_issue(evil_origin, "body")
        assert post.call_args.args[0].startswith("https://api.github.com/")

    @pytest.mark.asyncio
    async def test_malformed_origin_returns_false(self) -> None:
        svc = ReturnBottleService(AsyncMock(), _settings())
        factory, post = _mock_async_client()
        with patch("app.services.return_bottle_service.httpx.AsyncClient", factory):
            ok = await svc.post_to_github_issue({"repo": "no-slash"}, "body")
        assert ok is False
        post.assert_not_called()


class TestReport:
    @pytest.mark.asyncio
    async def test_no_origin_no_comment(self) -> None:
        svc = ReturnBottleService(AsyncMock(), _settings())
        log_book = AsyncMock()
        result = await svc.report(_voyage(origin=None, target_repo=None), log_book=log_book)
        assert result["issue_commented"] is False
        log_book.record.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_github_origin_no_comment(self) -> None:
        svc = ReturnBottleService(AsyncMock(), _settings())
        result = await svc.report(_voyage(origin={"type": "email"}), log_book=AsyncMock())
        assert result["issue_commented"] is False

    @pytest.mark.asyncio
    async def test_no_target_repo_no_log_book_write(self) -> None:
        svc = ReturnBottleService(AsyncMock(), _settings())
        log_book = AsyncMock()
        factory, _post = _mock_async_client(status_code=201)
        with patch("app.services.return_bottle_service.httpx.AsyncClient", factory):
            result = await svc.report(
                _voyage(origin=_github_origin(), target_repo=None),
                log_book=log_book,
            )
        assert result["log_book_recorded"] is False
        log_book.record.assert_not_called()

    @pytest.mark.asyncio
    async def test_both_present_both_attempted(self) -> None:
        svc = ReturnBottleService(AsyncMock(), _settings())
        log_book = AsyncMock()
        log_book.record = AsyncMock(return_value=MagicMock())
        factory, post = _mock_async_client(status_code=201)
        with patch("app.services.return_bottle_service.httpx.AsyncClient", factory):
            result = await svc.report(
                _voyage(origin=_github_origin(), target_repo="acme/widgets"),
                deployment_url="https://preview.dev/x",
                duration_seconds=5.0,
                phase_count=2,
                log_book=log_book,
            )
        assert result == {"issue_commented": True, "log_book_recorded": True}
        post.assert_awaited_once()
        log_book.record.assert_awaited_once()
        # Log Book write is a `summary` for the target repo.
        assert log_book.record.call_args.args[0] == "acme/widgets"
        assert log_book.record.call_args.args[2] == "summary"

    @pytest.mark.asyncio
    async def test_httpx_exception_swallowed(self) -> None:
        svc = ReturnBottleService(AsyncMock(), _settings())
        log_book = AsyncMock()
        log_book.record = AsyncMock(return_value=MagicMock())
        factory = MagicMock()
        client = MagicMock()
        client.__aenter__ = AsyncMock(side_effect=RuntimeError("network down"))
        client.__aexit__ = AsyncMock(return_value=None)
        factory.return_value = client
        with patch("app.services.return_bottle_service.httpx.AsyncClient", factory):
            result = await svc.report(
                _voyage(origin=_github_origin(), target_repo="acme/widgets"),
                log_book=log_book,
            )
        # Issue comment failed (swallowed) but Log Book still written.
        assert result["issue_commented"] is False
        assert result["log_book_recorded"] is True

    @pytest.mark.asyncio
    async def test_log_book_exception_swallowed(self) -> None:
        svc = ReturnBottleService(AsyncMock(), _settings())
        log_book = AsyncMock()
        log_book.record = AsyncMock(side_effect=RuntimeError("db down"))
        result = await svc.report(
            _voyage(origin=None, target_repo="acme/widgets"),
            log_book=log_book,
        )
        assert result["log_book_recorded"] is False

    @pytest.mark.asyncio
    async def test_builds_log_book_service_from_session_when_not_passed(self) -> None:
        session = AsyncMock()
        svc = ReturnBottleService(session, _settings())
        record = AsyncMock(return_value=MagicMock())
        with patch("app.services.return_bottle_service.LogBookService") as lb_cls:
            lb_cls.return_value.record = record
            result = await svc.report(_voyage(origin=None, target_repo="acme/widgets"))
        lb_cls.assert_called_once_with(session)
        record.assert_awaited_once()
        assert result["log_book_recorded"] is True
