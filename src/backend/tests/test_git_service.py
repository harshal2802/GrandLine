"""Tests for GitService (mocked ExecutionBackend)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.execution import ExecutionResult
from app.services.git_service import GitError, GitService

VOYAGE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
VOYAGE_HEX8 = VOYAGE_ID.hex[:8]
REPO_URL = "https://github.com/owner/repo.git"


def _exec_result(
    stdout: str = "", stderr: str = "", exit_code: int = 0, sandbox_id: str = "sandbox-git-1"
) -> ExecutionResult:
    return ExecutionResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=False,
        duration_seconds=0.1,
        sandbox_id=sandbox_id,
    )


@pytest.fixture
def mock_backend() -> AsyncMock:
    backend = AsyncMock()
    backend.create = AsyncMock(return_value="sandbox-git-1")
    backend.execute = AsyncMock(return_value=_exec_result())
    backend.destroy = AsyncMock()
    backend.status = AsyncMock()
    return backend


@pytest.fixture
def mock_settings() -> MagicMock:
    s = MagicMock()
    s.github_api_token = "ghp_test_token_123"
    s.git_default_branch = "main"
    s.git_author_name = "GrandLine Crew"
    s.git_author_email = "crew@grandline.dev"
    return s


@pytest.fixture
def service(mock_backend: AsyncMock, mock_settings: MagicMock) -> GitService:
    return GitService(mock_backend, mock_settings)


class TestCloneRepo:
    @pytest.mark.asyncio
    async def test_clone_creates_sandbox_and_runs_clone(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        result = await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        mock_backend.create.assert_awaited_once_with(USER_ID)
        assert mock_backend.execute.await_count >= 1
        assert result.sandbox_id == "sandbox-git-1"
        assert result.repo_url == REPO_URL

    @pytest.mark.asyncio
    async def test_clone_configures_git_author(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        commands = [call.args[1].command for call in mock_backend.execute.call_args_list]
        config_cmds = " ".join(commands)
        assert "user.name" in config_cmds
        assert "user.email" in config_cmds

    @pytest.mark.asyncio
    async def test_clone_injects_github_token_in_url(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        clone_call = mock_backend.execute.call_args_list[0]
        clone_cmd = clone_call.args[1].command
        assert "ghp_test_token_123" in clone_cmd
        assert "x-access-token" in clone_cmd

    @pytest.mark.asyncio
    async def test_clone_already_cloned_raises(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        with pytest.raises(GitError, match="REPO_ALREADY_CLONED"):
            await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)


class TestCreateBranch:
    @pytest.mark.asyncio
    async def test_naming_convention(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        result = await service.create_branch(VOYAGE_ID, USER_ID, "shipwright", "main")

        expected_name = f"agent/shipwright/{VOYAGE_HEX8}"
        assert result.name == expected_name
        assert result.is_current is True

    @pytest.mark.asyncio
    async def test_before_clone_raises(self, service: GitService) -> None:
        with pytest.raises(GitError, match="REPO_NOT_CLONED"):
            await service.create_branch(VOYAGE_ID, USER_ID, "shipwright", "main")

    @pytest.mark.asyncio
    async def test_runs_checkout(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()

        await service.create_branch(VOYAGE_ID, USER_ID, "shipwright", "main")

        cmd = mock_backend.execute.call_args.args[1].command
        assert "checkout -b" in cmd
        assert f"agent/shipwright/{VOYAGE_HEX8}" in cmd


class TestListBranches:
    @pytest.mark.asyncio
    async def test_parses_output(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()
        mock_backend.execute.return_value = _exec_result(
            stdout="main \nagent/shipwright/abc12345 *\n"
        )

        branches = await service.list_branches(VOYAGE_ID, USER_ID)

        assert len(branches) == 2
        assert branches[0].name == "main"
        assert branches[0].is_current is False
        assert branches[1].name == "agent/shipwright/abc12345"
        assert branches[1].is_current is True


class TestCommit:
    @pytest.mark.asyncio
    async def test_stages_and_commits(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()
        mock_backend.execute.return_value = _exec_result(
            stdout="abc123def456 abc123d 2026-04-12T10:00:00+00:00\n"
        )

        await service.commit(VOYAGE_ID, USER_ID, "feat: add login", "shipwright")

        commands = [call.args[1].command for call in mock_backend.execute.call_args_list]
        full_cmds = " ".join(commands)
        assert "git add" in full_cmds
        assert "git commit" in full_cmds
        assert "feat: add login" in full_cmds

    @pytest.mark.asyncio
    async def test_with_files_injects_files(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()
        mock_backend.execute.return_value = _exec_result(
            stdout="abc123def456 abc123d 2026-04-12T10:00:00+00:00\n"
        )

        files = {"main.py": "print('hello')"}
        await service.commit(VOYAGE_ID, USER_ID, "feat: add main", "shipwright", files)

        # Files should be prefixed with repo/ for put_archive at /workspace
        file_inject_call = mock_backend.execute.call_args_list[0]
        assert file_inject_call.args[1].files == {"repo/main.py": "print('hello')"}


class TestPush:
    @pytest.mark.asyncio
    async def test_runs_push_command(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()

        result = await service.push(VOYAGE_ID, USER_ID, "agent/shipwright/abc12345")

        cmd = mock_backend.execute.call_args.args[1].command
        assert "git push" in cmd
        assert "agent/shipwright/abc12345" in cmd
        assert result.pushed is True


class TestCreatePR:
    @pytest.mark.asyncio
    async def test_calls_github_api(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "number": 42,
            "html_url": "https://github.com/owner/repo/pull/42",
            "title": "Add login",
            "head": {"ref": "agent/shipwright/abc12345"},
            "base": {"ref": "main"},
        }

        with patch("app.services.git_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await service.create_pr(
                VOYAGE_ID, USER_ID, "Add login", "PR body", "agent/shipwright/abc12345", "main"
            )

        assert result.number == 42
        assert result.url == "https://github.com/owner/repo/pull/42"

    @pytest.mark.asyncio
    async def test_parses_response(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "number": 7,
            "html_url": "https://github.com/owner/repo/pull/7",
            "title": "feat: test",
            "head": {"ref": "feat/test"},
            "base": {"ref": "main"},
        }

        with patch("app.services.git_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await service.create_pr(
                VOYAGE_ID, USER_ID, "feat: test", "", "feat/test", "main"
            )

        assert result.title == "feat: test"
        assert result.head == "feat/test"
        assert result.base == "main"

    @pytest.mark.asyncio
    async def test_handles_api_error(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.text = "Validation Failed"
        mock_response.json.return_value = {"message": "Validation Failed"}

        with patch("app.services.git_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(GitError, match="GITHUB_API_ERROR"):
                await service.create_pr(VOYAGE_ID, USER_ID, "title", "", "feat/test", "main")


class TestGetLog:
    @pytest.mark.asyncio
    async def test_parses_output(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()
        mock_backend.execute.return_value = _exec_result(
            stdout=(
                "abc123def456\x00abc123d\x00feat: add login"
                "\x00shipwright\x002026-04-12T10:00:00+00:00\n"
                "def789abc012\x00def789a\x00fix: typo"
                "\x00doctor\x002026-04-12T09:00:00+00:00\n"
            )
        )

        log = await service.get_log(VOYAGE_ID, USER_ID, "main", limit=20)

        assert len(log) == 2
        assert log[0].sha == "abc123def456"
        assert log[0].short_sha == "abc123d"
        assert log[0].message == "feat: add login"
        assert log[0].author == "shipwright"
        assert log[1].sha == "def789abc012"


class TestCheckConflicts:
    @pytest.mark.asyncio
    async def test_no_conflicts(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()
        # Simulate: fetch succeeds, merge succeeds (exit 0), abort
        mock_backend.execute.side_effect = [
            _exec_result(),  # git fetch
            _exec_result(),  # git checkout
            _exec_result(stdout="EXIT:0\n"),  # git merge --no-commit --no-ff
            _exec_result(),  # git merge --abort
        ]

        result = await service.check_conflicts(VOYAGE_ID, USER_ID, "feat/test", "main")

        assert result.has_conflicts is False
        assert result.conflicting_files == []

    @pytest.mark.asyncio
    async def test_with_conflicts(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()
        mock_backend.execute.side_effect = [
            _exec_result(),  # git fetch
            _exec_result(),  # git checkout
            _exec_result(stdout="CONFLICT (content): Merge conflict in src/main.py\nEXIT:1\n"),
            _exec_result(stdout="src/main.py\nREADME.md\n"),  # git diff --name-only
            _exec_result(),  # git merge --abort
        ]

        result = await service.check_conflicts(VOYAGE_ID, USER_ID, "feat/test", "main")

        assert result.has_conflicts is True
        assert "src/main.py" in result.conflicting_files

    @pytest.mark.asyncio
    async def test_aborts_merge(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()
        mock_backend.execute.side_effect = [
            _exec_result(),  # git fetch
            _exec_result(),  # git checkout
            _exec_result(stdout="EXIT:0\n"),  # no conflicts
            _exec_result(),  # git merge --abort
        ]

        await service.check_conflicts(VOYAGE_ID, USER_ID, "feat/test", "main")

        commands = [call.args[1].command for call in mock_backend.execute.call_args_list]
        assert any("merge --abort" in cmd for cmd in commands)


class TestCleanupBranches:
    @pytest.mark.asyncio
    async def test_destroys_sandbox(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()
        mock_backend.execute.return_value = _exec_result()

        await service.cleanup_branches(VOYAGE_ID, USER_ID)

        mock_backend.destroy.assert_awaited_once_with("sandbox-git-1")


class TestCleanupAll:
    @pytest.mark.asyncio
    async def test_destroys_all(self, service: GitService, mock_backend: AsyncMock) -> None:
        other_voyage = uuid.uuid4()
        mock_backend.create.side_effect = ["sandbox-git-1", "sandbox-git-2"]
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        await service.clone_repo(other_voyage, USER_ID, REPO_URL)

        await service.cleanup_all()

        assert mock_backend.destroy.await_count == 2

    @pytest.mark.asyncio
    async def test_continues_on_error(self, service: GitService, mock_backend: AsyncMock) -> None:
        other_voyage = uuid.uuid4()
        mock_backend.create.side_effect = ["sandbox-git-1", "sandbox-git-2"]
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        await service.clone_repo(other_voyage, USER_ID, REPO_URL)

        mock_backend.destroy.side_effect = [Exception("fail"), None]

        await service.cleanup_all()

        assert mock_backend.destroy.await_count == 2


class TestBranchNameValidation:
    @pytest.mark.asyncio
    async def test_rejects_injection(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        with pytest.raises(GitError, match="INVALID_BRANCH_NAME"):
            await service.create_branch(VOYAGE_ID, USER_ID, "; rm -rf /", "main")

    @pytest.mark.asyncio
    async def test_push_validates_branch(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        with pytest.raises(GitError, match="INVALID_BRANCH_NAME"):
            await service.push(VOYAGE_ID, USER_ID, "; rm -rf /")

    @pytest.mark.asyncio
    async def test_get_log_validates_branch(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        with pytest.raises(GitError, match="INVALID_BRANCH_NAME"):
            await service.get_log(VOYAGE_ID, USER_ID, "$(whoami)")

    @pytest.mark.asyncio
    async def test_check_conflicts_validates_branches(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        with pytest.raises(GitError, match="INVALID_BRANCH_NAME"):
            await service.check_conflicts(VOYAGE_ID, USER_ID, "; cat /etc/passwd", "main")


class TestInjectToken:
    def test_preserves_port(self) -> None:
        from app.services.git_service import _inject_token

        result = _inject_token("https://github.example.com:8443/owner/repo.git", "tok123")
        assert result == "https://x-access-token:tok123@github.example.com:8443/owner/repo.git"

    def test_standard_url(self) -> None:
        from app.services.git_service import _inject_token

        result = _inject_token("https://github.com/owner/repo.git", "tok123")
        assert result == "https://x-access-token:tok123@github.com/owner/repo.git"
