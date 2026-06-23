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
    s.git_allowed_hosts = None  # use default ALLOWED_GIT_HOSTS
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

    @pytest.mark.asyncio
    async def test_clone_rejects_disallowed_host(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        with pytest.raises(GitError, match="DISALLOWED_HOST"):
            await service.clone_repo(VOYAGE_ID, USER_ID, "https://evil.com/repo.git")
        mock_backend.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_clone_accepts_allowed_hosts(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        for host in ("github.com", "gitlab.com", "bitbucket.org"):
            svc = GitService(mock_backend, service._settings)
            vid = uuid.uuid4()
            result = await svc.clone_repo(vid, USER_ID, f"https://{host}/owner/repo.git")
            assert result.sandbox_id == "sandbox-git-1"


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

    @pytest.mark.asyncio
    async def test_branches_from_remote_tracking(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()

        await service.create_branch(VOYAGE_ID, USER_ID, "shipwright", "main")

        cmd = mock_backend.execute.call_args.args[1].command
        assert "origin/main" in cmd


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


class TestGetHeadSha:
    @pytest.mark.asyncio
    async def test_returns_stripped_sha(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute = AsyncMock(return_value=_exec_result(stdout="deadbeef1234\n"))

        sha = await service.get_head_sha(VOYAGE_ID, USER_ID, "main")

        assert sha == "deadbeef1234"
        cmd = mock_backend.execute.call_args.args[1].command
        assert "rev-parse" in cmd
        assert "main" in cmd

    @pytest.mark.asyncio
    async def test_rejects_shell_metacharacters_in_ref(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        with pytest.raises(GitError, match="INVALID_BRANCH_NAME"):
            await service.get_head_sha(VOYAGE_ID, USER_ID, "$(whoami)")


class TestListChangedFiles:
    @pytest.mark.asyncio
    async def test_parses_name_status(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()
        mock_backend.execute.return_value = _exec_result(
            stdout="A\tsrc/new.py\nM\tsrc/main.py\nD\tsrc/old.py\n"
        )

        files = await service.list_changed_files(VOYAGE_ID, USER_ID, "main", "feat/test")

        assert len(files) == 3
        assert files[0].status == "A"
        assert files[0].path == "src/new.py"
        assert files[1].status == "M"
        assert files[2].status == "D"

    @pytest.mark.asyncio
    async def test_parses_rename_uses_new_path(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()
        mock_backend.execute.return_value = _exec_result(
            stdout="R100\tsrc/old_name.py\tsrc/new_name.py\n"
        )

        files = await service.list_changed_files(VOYAGE_ID, USER_ID, "main", "feat/test")

        assert len(files) == 1
        assert files[0].status == "R100"
        assert files[0].path == "src/new_name.py"

    @pytest.mark.asyncio
    async def test_builds_three_dot_argv(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()
        mock_backend.execute.return_value = _exec_result(stdout="")

        await service.list_changed_files(VOYAGE_ID, USER_ID, "main", "feat/test")

        cmd = mock_backend.execute.call_args.args[1].command
        assert "git diff --name-status" in cmd
        assert "main...feat/test" in cmd

    @pytest.mark.asyncio
    async def test_validates_refs(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        with pytest.raises(GitError, match="INVALID_BRANCH_NAME"):
            await service.list_changed_files(VOYAGE_ID, USER_ID, "main", "$(rm -rf /)")


class TestDiff:
    @pytest.mark.asyncio
    async def test_whole_branch(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()
        mock_backend.execute.return_value = _exec_result(
            stdout="diff --git a/x b/x\n+added\n-removed\n"
        )

        result = await service.diff(VOYAGE_ID, USER_ID, "main", "feat/test")

        assert result.base == "main"
        assert result.head == "feat/test"
        assert result.path is None
        assert "+added" in result.unified
        cmd = mock_backend.execute.call_args.args[1].command
        assert "git diff main...feat/test" in cmd
        assert " -- " not in cmd

    @pytest.mark.asyncio
    async def test_single_file_adds_pathspec(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()
        mock_backend.execute.return_value = _exec_result(stdout="diff…")

        result = await service.diff(VOYAGE_ID, USER_ID, "main", "feat/test", path="src/main.py")

        assert result.path == "src/main.py"
        cmd = mock_backend.execute.call_args.args[1].command
        assert "-- src/main.py" in cmd

    @pytest.mark.asyncio
    async def test_validates_refs(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        with pytest.raises(GitError, match="INVALID_BRANCH_NAME"):
            await service.diff(VOYAGE_ID, USER_ID, "; whoami", "feat/test")

    @pytest.mark.asyncio
    async def test_rejects_path_traversal(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        with pytest.raises(GitError, match="INVALID_PATH"):
            await service.diff(VOYAGE_ID, USER_ID, "main", "feat/test", path="../../etc/passwd")

    @pytest.mark.asyncio
    async def test_rejects_absolute_path(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        with pytest.raises(GitError, match="INVALID_PATH"):
            await service.diff(VOYAGE_ID, USER_ID, "main", "feat/test", path="/etc/passwd")


class TestGetFileContent:
    @pytest.mark.asyncio
    async def test_returns_content(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()
        mock_backend.execute.return_value = _exec_result(stdout="print('hello')\n")

        result = await service.get_file_content(VOYAGE_ID, USER_ID, "feat/test", "src/main.py")

        assert result.ref == "feat/test"
        assert result.path == "src/main.py"
        assert result.content == "print('hello')\n"
        cmd = mock_backend.execute.call_args.args[1].command
        assert "git show" in cmd
        assert "feat/test:src/main.py" in cmd

    @pytest.mark.asyncio
    async def test_validates_ref(self, service: GitService, mock_backend: AsyncMock) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        with pytest.raises(GitError, match="INVALID_BRANCH_NAME"):
            await service.get_file_content(VOYAGE_ID, USER_ID, "$(id)", "src/main.py")

    @pytest.mark.asyncio
    async def test_rejects_path_traversal(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        with pytest.raises(GitError, match="INVALID_PATH"):
            await service.get_file_content(VOYAGE_ID, USER_ID, "main", "../../../etc/passwd")


class TestInjectToken:
    def test_preserves_port(self) -> None:
        from app.services.git_service import _inject_token

        result = _inject_token("https://github.example.com:8443/owner/repo.git", "tok123")
        assert result == "https://x-access-token:tok123@github.example.com:8443/owner/repo.git"

    def test_standard_url(self) -> None:
        from app.services.git_service import _inject_token

        result = _inject_token("https://github.com/owner/repo.git", "tok123")
        assert result == "https://x-access-token:tok123@github.com/owner/repo.git"


class TestPerUserTokenOverride:
    """Phase A3: a provided per-user token overrides the env token; None preserves it."""

    @pytest.mark.asyncio
    async def test_clone_uses_per_user_token_when_provided(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL, token="gho_user_token")

        clone_cmd = mock_backend.execute.call_args_list[0].args[1].command
        # The user's token is injected into the clone URL — NOT the env token.
        assert "gho_user_token" in clone_cmd
        assert "ghp_test_token_123" not in clone_cmd
        assert "x-access-token" in clone_cmd

    @pytest.mark.asyncio
    async def test_clone_falls_back_to_env_token_when_none(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)  # token defaults to None

        clone_cmd = mock_backend.execute.call_args_list[0].args[1].command
        assert "ghp_test_token_123" in clone_cmd

    @pytest.mark.asyncio
    async def test_push_uses_per_user_token_authenticated_remote(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()

        await service.push(VOYAGE_ID, USER_ID, "feat/x", token="gho_user_token")

        push_cmd = mock_backend.execute.call_args.args[1].command
        assert "gho_user_token" in push_cmd
        assert "x-access-token" in push_cmd

    @pytest.mark.asyncio
    async def test_push_falls_back_to_origin_when_none(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()

        await service.push(VOYAGE_ID, USER_ID, "feat/x")

        push_cmd = mock_backend.execute.call_args.args[1].command
        assert "git push origin" in push_cmd
        assert "x-access-token" not in push_cmd

    @pytest.mark.asyncio
    async def test_create_pr_uses_per_user_token_in_authorization(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "number": 9,
            "html_url": "https://github.com/owner/repo/pull/9",
            "title": "t",
            "head": {"ref": "feat/x"},
            "base": {"ref": "main"},
        }
        with patch("app.services.git_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await service.create_pr(
                VOYAGE_ID, USER_ID, "t", "", "feat/x", "main", token="gho_user_token"
            )

        headers = mock_client.post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer gho_user_token"

    @pytest.mark.asyncio
    async def test_create_pr_falls_back_to_env_token_when_none(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "number": 9,
            "html_url": "https://github.com/owner/repo/pull/9",
            "title": "t",
            "head": {"ref": "feat/x"},
            "base": {"ref": "main"},
        }
        with patch("app.services.git_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await service.create_pr(VOYAGE_ID, USER_ID, "t", "", "feat/x", "main")

        headers = mock_client.post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer ghp_test_token_123"

    @pytest.mark.asyncio
    async def test_commit_uses_author_login_identity(
        self, service: GitService, mock_backend: AsyncMock
    ) -> None:
        await service.clone_repo(VOYAGE_ID, USER_ID, REPO_URL)
        mock_backend.execute.reset_mock()
        mock_backend.execute.return_value = _exec_result(
            stdout="abc123 abc123d 2026-06-22T00:00:00+00:00"
        )

        result = await service.commit(VOYAGE_ID, USER_ID, "msg", "shipwright", author_login="luffy")

        commit_cmd = " ".join(call.args[1].command for call in mock_backend.execute.call_args_list)
        assert "luffy" in commit_cmd
        assert result.author == "luffy"
