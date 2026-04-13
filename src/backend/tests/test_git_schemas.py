"""Tests for Git Integration schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.git import (
    GitBranchInfo,
    GitBranchRequest,
    GitCloneRequest,
    GitCommitInfo,
    GitCommitRequest,
    GitConflictCheckRequest,
    GitConflictInfo,
    GitPRInfo,
    GitPRRequest,
    GitPushInfo,
    GitPushRequest,
    GitRepoInfo,
)


class TestGitCloneRequest:
    def test_defaults(self) -> None:
        req = GitCloneRequest()
        assert req.repo_url is None

    def test_rejects_non_https(self) -> None:
        with pytest.raises(ValidationError):
            GitCloneRequest(repo_url="file:///tmp/repo")

    def test_rejects_ssh(self) -> None:
        with pytest.raises(ValidationError):
            GitCloneRequest(repo_url="ssh://git@github.com/owner/repo.git")

    def test_rejects_git_protocol(self) -> None:
        with pytest.raises(ValidationError):
            GitCloneRequest(repo_url="git://github.com/owner/repo.git")

    def test_accepts_https(self) -> None:
        req = GitCloneRequest(repo_url="https://github.com/owner/repo.git")
        assert req.repo_url == "https://github.com/owner/repo.git"


class TestGitBranchRequest:
    def test_defaults(self) -> None:
        req = GitBranchRequest(crew_member="shipwright")
        assert req.base_branch == "main"
        assert req.crew_member == "shipwright"


class TestGitCommitRequest:
    def test_defaults(self) -> None:
        req = GitCommitRequest(message="feat: add login", crew_member="shipwright")
        assert req.files == {}

    def test_message_min_length(self) -> None:
        with pytest.raises(ValidationError):
            GitCommitRequest(message="", crew_member="shipwright")

    def test_message_max_length(self) -> None:
        with pytest.raises(ValidationError):
            GitCommitRequest(message="x" * 501, crew_member="shipwright")


class TestGitPRRequest:
    def test_title_min_length(self) -> None:
        with pytest.raises(ValidationError):
            GitPRRequest(title="", head_branch="feat/test")

    def test_title_max_length(self) -> None:
        with pytest.raises(ValidationError):
            GitPRRequest(title="x" * 201, head_branch="feat/test")

    def test_defaults(self) -> None:
        req = GitPRRequest(title="Add login", head_branch="agent/shipwright/abc12345")
        assert req.body == ""
        assert req.base_branch == "main"


class TestGitPushRequest:
    def test_fields(self) -> None:
        req = GitPushRequest(branch="agent/shipwright/abc12345")
        assert req.branch == "agent/shipwright/abc12345"


class TestGitConflictCheckRequest:
    def test_defaults(self) -> None:
        req = GitConflictCheckRequest(branch="agent/shipwright/abc12345")
        assert req.target_branch == "main"


class TestResponseSchemas:
    def test_repo_info(self) -> None:
        info = GitRepoInfo(
            sandbox_id="abc123",
            repo_url="https://github.com/owner/repo.git",
            default_branch="main",
        )
        assert info.sandbox_id == "abc123"

    def test_branch_info(self) -> None:
        info = GitBranchInfo(name="agent/shipwright/abc12345", is_current=True)
        assert info.is_current is True

    def test_commit_info(self) -> None:
        info = GitCommitInfo(
            sha="abc123def456",
            short_sha="abc123d",
            message="feat: add login",
            author="shipwright",
            timestamp="2026-04-12T10:00:00+00:00",
        )
        assert info.sha == "abc123def456"

    def test_push_info(self) -> None:
        info = GitPushInfo(branch="main", pushed=True)
        assert info.pushed is True

    def test_pr_info(self) -> None:
        info = GitPRInfo(
            number=42,
            url="https://github.com/owner/repo/pull/42",
            title="Add login",
            head="agent/shipwright/abc12345",
            base="main",
        )
        assert info.number == 42

    def test_conflict_info_no_conflicts(self) -> None:
        info = GitConflictInfo(has_conflicts=False)
        assert info.conflicting_files == []

    def test_conflict_info_with_conflicts(self) -> None:
        info = GitConflictInfo(
            has_conflicts=True,
            conflicting_files=["src/main.py", "README.md"],
        )
        assert len(info.conflicting_files) == 2
