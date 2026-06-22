"""Tests for TriggerService (mocked AsyncSession + patched settings — no DB)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.dial_config import DialConfig
from app.models.enums import VoyageStatus
from app.models.voyage import Voyage
from app.schemas.trigger import GithubIssueWebhook
from app.services.trigger_service import TriggerError, TriggerService

USER_ID = uuid.uuid4()


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _scalar_one_or_none(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _payload(
    *,
    action: str = "opened",
    labels: list[str] | None = None,
    title: str = "Login button does nothing",
    body: str | None = "Repro steps",
    clone_url: str | None = "https://github.com/acme/widgets.git",
) -> GithubIssueWebhook:
    return GithubIssueWebhook.model_validate(
        {
            "action": action,
            "issue": {
                "number": 42,
                "title": title,
                "body": body,
                "html_url": "https://github.com/acme/widgets/issues/42",
                "labels": [{"name": n} for n in (labels or [])],
            },
            "repository": {"full_name": "acme/widgets", "clone_url": clone_url},
            "sender": {"login": "reporter"},
        }
    )


class TestShouldTrigger:
    def test_opened_with_label_triggers(self) -> None:
        with patch("app.services.trigger_service.settings.trigger_label", "grandline"):
            assert TriggerService.should_trigger(_payload(labels=["bug", "grandline"]))

    def test_labeled_with_label_triggers(self) -> None:
        with patch("app.services.trigger_service.settings.trigger_label", "grandline"):
            assert TriggerService.should_trigger(
                _payload(action="labeled", labels=["grandline"])
            )

    def test_missing_label_ignored(self) -> None:
        with patch("app.services.trigger_service.settings.trigger_label", "grandline"):
            assert not TriggerService.should_trigger(_payload(labels=["bug"]))

    def test_non_trigger_action_ignored(self) -> None:
        with patch("app.services.trigger_service.settings.trigger_label", "grandline"):
            assert not TriggerService.should_trigger(
                _payload(action="closed", labels=["grandline"])
            )


class TestResolveTriggerUser:
    @pytest.mark.asyncio
    async def test_unconfigured_email_raises(self) -> None:
        session = _mock_session()
        service = TriggerService(session)
        with patch(
            "app.services.trigger_service.settings.trigger_default_user_email", None
        ):
            with pytest.raises(TriggerError) as exc:
                await service.resolve_trigger_user()
        assert exc.value.code == "TRIGGER_USER_UNCONFIGURED"

    @pytest.mark.asyncio
    async def test_user_not_found_raises(self) -> None:
        session = _mock_session()
        session.execute = AsyncMock(return_value=_scalar_one_or_none(None))
        service = TriggerService(session)
        with patch(
            "app.services.trigger_service.settings.trigger_default_user_email",
            "crew@grandline.dev",
        ):
            with pytest.raises(TriggerError) as exc:
                await service.resolve_trigger_user()
        assert exc.value.code == "TRIGGER_USER_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_returns_configured_user(self) -> None:
        user = MagicMock()
        user.id = USER_ID
        session = _mock_session()
        session.execute = AsyncMock(return_value=_scalar_one_or_none(user))
        service = TriggerService(session)
        with patch(
            "app.services.trigger_service.settings.trigger_default_user_email",
            "crew@grandline.dev",
        ):
            result = await service.resolve_trigger_user()
        assert result is user


class TestIngestGithubIssue:
    def _user(self) -> MagicMock:
        user = MagicMock()
        user.id = USER_ID
        return user

    @pytest.mark.asyncio
    async def test_creates_charted_voyage_with_origin(self) -> None:
        session = _mock_session()
        service = TriggerService(session)

        voyage = await service.ingest_github_issue(_payload(), self._user())

        assert isinstance(voyage, Voyage)
        assert voyage.status == VoyageStatus.CHARTED.value
        assert voyage.user_id == USER_ID
        assert voyage.title == "Login button does nothing"
        assert voyage.description == "Repro steps"
        assert voyage.target_repo == "https://github.com/acme/widgets.git"

        assert voyage.origin == {
            "type": "github_issue",
            "repo": "acme/widgets",
            "issue_number": 42,
            "issue_url": "https://github.com/acme/widgets/issues/42",
            "issue_title": "Login button does nothing",
            "sender": "reporter",
            "received_at": voyage.origin["received_at"],
        }
        # received_at is an ISO-8601 UTC timestamp.
        assert voyage.origin["received_at"].endswith("+00:00")

        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(voyage)

    @pytest.mark.asyncio
    async def test_seeds_default_dial_config(self) -> None:
        session = _mock_session()
        service = TriggerService(session)

        await service.ingest_github_issue(_payload(), self._user())

        added = [c.args[0] for c in session.add.call_args_list]
        assert any(isinstance(a, Voyage) for a in added)
        dial = next(a for a in added if isinstance(a, DialConfig))
        # Identical to a manual chart: every crew role mapped.
        assert "captain" in dial.role_mapping

    @pytest.mark.asyncio
    async def test_title_truncated_to_255(self) -> None:
        session = _mock_session()
        service = TriggerService(session)
        long_title = "x" * 400

        voyage = await service.ingest_github_issue(
            _payload(title=long_title), self._user()
        )

        assert len(voyage.title) == 255

    @pytest.mark.asyncio
    async def test_falls_back_to_full_name_without_clone_url(self) -> None:
        session = _mock_session()
        service = TriggerService(session)

        voyage = await service.ingest_github_issue(
            _payload(clone_url=None), self._user()
        )

        assert voyage.target_repo == "acme/widgets"

    @pytest.mark.asyncio
    async def test_null_body_yields_none_description(self) -> None:
        session = _mock_session()
        service = TriggerService(session)

        voyage = await service.ingest_github_issue(_payload(body=None), self._user())

        assert voyage.description is None


class TestReader:
    def test_reader_returns_instance(self) -> None:
        assert isinstance(TriggerService.reader(_mock_session()), TriggerService)
