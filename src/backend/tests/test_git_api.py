"""Tests for Git Integration REST API endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.schemas.git import (
    GitBranchInfo,
    GitCommitInfo,
    GitConflictInfo,
    GitPRInfo,
    GitPushInfo,
    GitRepoInfo,
)
from app.services.git_service import GitError

VOYAGE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = USER_ID
    return user


def _mock_voyage(target_repo: str | None = "https://github.com/owner/repo.git") -> MagicMock:
    voyage = MagicMock()
    voyage.id = VOYAGE_ID
    voyage.target_repo = target_repo
    return voyage


def _mock_git_service() -> AsyncMock:
    svc = AsyncMock()
    svc.clone_repo = AsyncMock(
        return_value=GitRepoInfo(
            sandbox_id="sandbox-git-1",
            repo_url="https://github.com/owner/repo.git",
            default_branch="main",
        )
    )
    svc.create_branch = AsyncMock(
        return_value=GitBranchInfo(name="agent/shipwright/abc12345", is_current=True)
    )
    svc.list_branches = AsyncMock(
        return_value=[
            GitBranchInfo(name="main", is_current=False),
            GitBranchInfo(name="agent/shipwright/abc12345", is_current=True),
        ]
    )
    svc.commit = AsyncMock(
        return_value=GitCommitInfo(
            sha="abc123def456",
            short_sha="abc123d",
            message="feat: add login",
            author="shipwright",
            timestamp="2026-04-12T10:00:00+00:00",
        )
    )
    svc.push = AsyncMock(return_value=GitPushInfo(branch="agent/shipwright/abc12345", pushed=True))
    svc.create_pr = AsyncMock(
        return_value=GitPRInfo(
            number=42,
            url="https://github.com/owner/repo/pull/42",
            title="Add login",
            head="agent/shipwright/abc12345",
            base="main",
        )
    )
    svc.get_log = AsyncMock(
        return_value=[
            GitCommitInfo(
                sha="abc123def456",
                short_sha="abc123d",
                message="feat: add login",
                author="shipwright",
                timestamp="2026-04-12T10:00:00+00:00",
            )
        ]
    )
    svc.check_conflicts = AsyncMock(
        return_value=GitConflictInfo(has_conflicts=False, conflicting_files=[])
    )
    svc.cleanup_branches = AsyncMock()
    return svc


class TestCloneEndpoint:
    @pytest.mark.asyncio
    async def test_clone_returns_repo_info(self) -> None:
        from app.api.v1.git import clone_repo
        from app.schemas.git import GitCloneRequest

        svc = _mock_git_service()
        body = GitCloneRequest(repo_url="https://github.com/owner/repo.git")
        result = await clone_repo(VOYAGE_ID, body, _mock_user(), _mock_voyage(), svc)

        assert result.sandbox_id == "sandbox-git-1"
        svc.clone_repo.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clone_uses_voyage_target_repo(self) -> None:
        from app.api.v1.git import clone_repo
        from app.schemas.git import GitCloneRequest

        svc = _mock_git_service()
        body = GitCloneRequest()  # repo_url=None
        voyage = _mock_voyage(target_repo="https://github.com/owner/other.git")
        await clone_repo(VOYAGE_ID, body, _mock_user(), voyage, svc)

        call_args = svc.clone_repo.call_args
        assert call_args.args[2] == "https://github.com/owner/other.git"

    @pytest.mark.asyncio
    async def test_clone_no_target_repo_400(self) -> None:
        from app.api.v1.git import clone_repo
        from app.schemas.git import GitCloneRequest

        svc = _mock_git_service()
        body = GitCloneRequest()  # repo_url=None
        voyage = _mock_voyage(target_repo=None)

        with pytest.raises(HTTPException) as exc_info:
            await clone_repo(VOYAGE_ID, body, _mock_user(), voyage, svc)

        assert exc_info.value.status_code == 400


class TestBranchEndpoints:
    @pytest.mark.asyncio
    async def test_create_branch_returns_info(self) -> None:
        from app.api.v1.git import create_branch
        from app.schemas.git import GitBranchRequest

        svc = _mock_git_service()
        body = GitBranchRequest(crew_member="shipwright")
        result = await create_branch(VOYAGE_ID, body, _mock_user(), _mock_voyage(), svc)

        assert result.name == "agent/shipwright/abc12345"
        assert result.is_current is True

    @pytest.mark.asyncio
    async def test_list_branches_returns_list(self) -> None:
        from app.api.v1.git import list_branches

        svc = _mock_git_service()
        result = await list_branches(VOYAGE_ID, _mock_user(), _mock_voyage(), svc)

        assert len(result) == 2


class TestCommitEndpoint:
    @pytest.mark.asyncio
    async def test_commit_returns_info(self) -> None:
        from app.api.v1.git import commit_changes
        from app.schemas.git import GitCommitRequest

        svc = _mock_git_service()
        body = GitCommitRequest(message="feat: add login", crew_member="shipwright")
        result = await commit_changes(VOYAGE_ID, body, _mock_user(), _mock_voyage(), svc)

        assert result.sha == "abc123def456"


class TestPushEndpoint:
    @pytest.mark.asyncio
    async def test_push_returns_info(self) -> None:
        from app.api.v1.git import push_branch
        from app.schemas.git import GitPushRequest

        svc = _mock_git_service()
        body = GitPushRequest(branch="agent/shipwright/abc12345")
        result = await push_branch(VOYAGE_ID, body, _mock_user(), _mock_voyage(), svc)

        assert result.pushed is True


class TestPREndpoint:
    @pytest.mark.asyncio
    async def test_create_pr_returns_info(self) -> None:
        from app.api.v1.git import create_pull_request
        from app.schemas.git import GitPRRequest

        svc = _mock_git_service()
        body = GitPRRequest(title="Add login", head_branch="agent/shipwright/abc12345")
        result = await create_pull_request(VOYAGE_ID, body, _mock_user(), _mock_voyage(), svc)

        assert result.number == 42


class TestLogEndpoint:
    @pytest.mark.asyncio
    async def test_get_log_returns_entries(self) -> None:
        from app.api.v1.git import get_log

        svc = _mock_git_service()
        result = await get_log(VOYAGE_ID, "main", 20, _mock_user(), _mock_voyage(), svc)

        assert len(result) == 1
        assert result[0].sha == "abc123def456"


class TestConflictsEndpoint:
    @pytest.mark.asyncio
    async def test_check_conflicts_returns_info(self) -> None:
        from app.api.v1.git import check_conflicts
        from app.schemas.git import GitConflictCheckRequest

        svc = _mock_git_service()
        body = GitConflictCheckRequest(branch="feat/test")
        result = await check_conflicts(VOYAGE_ID, body, _mock_user(), _mock_voyage(), svc)

        assert result.has_conflicts is False


class TestCleanupEndpoint:
    @pytest.mark.asyncio
    async def test_cleanup_branches_204(self) -> None:
        from app.api.v1.git import cleanup_branches

        svc = _mock_git_service()
        await cleanup_branches(VOYAGE_ID, _mock_user(), _mock_voyage(), svc)

        svc.cleanup_branches.assert_awaited_once_with(VOYAGE_ID, USER_ID)


class TestErrorMapping:
    @pytest.mark.asyncio
    async def test_repo_not_cloned_409(self) -> None:
        from app.api.v1.git import list_branches

        svc = _mock_git_service()
        svc.list_branches.side_effect = GitError("REPO_NOT_CLONED")

        with pytest.raises(HTTPException) as exc_info:
            await list_branches(VOYAGE_ID, _mock_user(), _mock_voyage(), svc)

        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_github_api_error_502(self) -> None:
        from app.api.v1.git import create_pull_request
        from app.schemas.git import GitPRRequest

        svc = _mock_git_service()
        svc.create_pr.side_effect = GitError("GITHUB_API_ERROR: 422 Validation Failed")

        body = GitPRRequest(title="Add login", head_branch="feat/test")
        with pytest.raises(HTTPException) as exc_info:
            await create_pull_request(VOYAGE_ID, body, _mock_user(), _mock_voyage(), svc)

        assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_unauthorized_401(self) -> None:
        from app.api.v1.dependencies import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=None, session=AsyncMock())

        assert exc_info.value.status_code == 401
