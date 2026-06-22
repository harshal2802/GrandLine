"""Tests for the Message-in-a-Bottle trigger schemas (GitHub webhook subset)."""

from __future__ import annotations

import uuid

from app.schemas.trigger import GithubIssueWebhook, TriggerResult

# A realistic (trimmed) GitHub issues.opened payload with extra/unknown fields.
PAYLOAD = {
    "action": "opened",
    "issue": {
        "number": 42,
        "title": "Login button does nothing on Safari",
        "body": "Steps to reproduce...",
        "html_url": "https://github.com/acme/widgets/issues/42",
        "labels": [
            {"id": 1, "name": "bug", "color": "d73a4a"},
            {"id": 2, "name": "grandline", "color": "0e8a16"},
        ],
        "user": {"login": "reporter", "id": 99},
        "state": "open",
    },
    "repository": {
        "full_name": "acme/widgets",
        "clone_url": "https://github.com/acme/widgets.git",
        "private": False,
        "stargazers_count": 12,
    },
    "sender": {"login": "reporter", "id": 99, "type": "User"},
    "organization": {"login": "acme"},
}


class TestGithubIssueWebhook:
    def test_parses_realistic_payload_with_extra_fields(self) -> None:
        event = GithubIssueWebhook.model_validate(PAYLOAD)

        assert event.action == "opened"
        assert event.issue.number == 42
        assert event.issue.title == "Login button does nothing on Safari"
        assert event.issue.body == "Steps to reproduce..."
        assert event.issue.html_url == "https://github.com/acme/widgets/issues/42"
        assert event.repository.full_name == "acme/widgets"
        assert event.repository.clone_url == "https://github.com/acme/widgets.git"
        assert event.sender.login == "reporter"

    def test_labels_parsed(self) -> None:
        event = GithubIssueWebhook.model_validate(PAYLOAD)
        names = {label.name for label in event.issue.labels}
        assert names == {"bug", "grandline"}

    def test_null_body_and_missing_clone_url(self) -> None:
        payload = {
            "action": "labeled",
            "issue": {
                "number": 5,
                "title": "x",
                "body": None,
                "html_url": "https://github.com/acme/widgets/issues/5",
                "labels": [],
            },
            "repository": {"full_name": "acme/widgets"},
            "sender": {"login": "bot"},
        }
        event = GithubIssueWebhook.model_validate(payload)
        assert event.issue.body is None
        assert event.repository.clone_url is None
        assert event.issue.labels == []


class TestTriggerResult:
    def test_charted(self) -> None:
        vid = uuid.uuid4()
        result = TriggerResult(status="charted", voyage_id=vid)
        assert result.status == "charted"
        assert result.voyage_id == vid
        assert result.reason is None

    def test_ignored(self) -> None:
        result = TriggerResult(status="ignored", reason="not a trigger")
        assert result.status == "ignored"
        assert result.voyage_id is None
        assert result.reason == "not a trigger"
