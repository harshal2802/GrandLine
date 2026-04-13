"""Git Integration Service — manages per-voyage git sandboxes."""

from __future__ import annotations

import logging
import re
import shlex
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx

from app.execution.backend import ExecutionBackend
from app.schemas.execution import ExecutionRequest
from app.schemas.git import (
    GitBranchInfo,
    GitCommitInfo,
    GitConflictInfo,
    GitPRInfo,
    GitPushInfo,
    GitRepoInfo,
)

logger = logging.getLogger(__name__)

REPO_PATH = "/workspace/repo"
BRANCH_NAME_RE = re.compile(r"^[a-zA-Z0-9/_.\-]+$")
ALLOWED_GIT_HOSTS = frozenset({"github.com", "gitlab.com", "bitbucket.org"})


class GitError(Exception):
    """Raised when a git operation fails."""


def _branch_name(crew_member: str, voyage_id: uuid.UUID) -> str:
    return f"agent/{crew_member}/{voyage_id.hex[:8]}"


def _validate_branch_component(value: str) -> None:
    if not BRANCH_NAME_RE.match(value):
        raise GitError(f"INVALID_BRANCH_NAME: {value!r} contains invalid characters")


def _validate_repo_host(repo_url: str, allowed_hosts: frozenset[str]) -> None:
    """Reject repo URLs whose host is not in the allowlist."""
    parsed = urlparse(repo_url)
    hostname = (parsed.hostname or "").lower()
    if hostname not in allowed_hosts:
        raise GitError(f"DISALLOWED_HOST: {hostname!r} is not an allowed git host")


def _inject_token(repo_url: str, token: str) -> str:
    """Rewrite HTTPS URL to include authentication token."""
    parsed = urlparse(repo_url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    return f"https://x-access-token:{token}@{host}{port}{parsed.path}"


def _parse_owner_repo(repo_url: str) -> str:
    """Extract owner/repo from a GitHub URL."""
    parsed = urlparse(repo_url)
    path = parsed.path.rstrip("/").removesuffix(".git")
    return path.lstrip("/")


class GitService:
    def __init__(self, backend: ExecutionBackend, settings: Any) -> None:
        self._backend = backend
        self._settings = settings
        self._repos: dict[uuid.UUID, str] = {}  # voyage_id -> sandbox_id
        self._repo_urls: dict[uuid.UUID, str] = {}  # voyage_id -> original repo URL

    async def _run(self, sandbox_id: str, command: str, **kwargs: Any) -> str:
        """Execute a command in the sandbox and return stdout."""
        request = ExecutionRequest(command=command, **kwargs)
        result = await self._backend.execute(sandbox_id, request)
        if result.exit_code != 0:
            raise GitError(f"Git command failed (exit {result.exit_code}): {result.stderr.strip()}")
        return result.stdout

    async def _run_unchecked(self, sandbox_id: str, command: str, **kwargs: Any) -> tuple[str, int]:
        """Execute a command and return (stdout, exit_code) without raising on non-zero."""
        request = ExecutionRequest(command=command, **kwargs)
        result = await self._backend.execute(sandbox_id, request)
        return result.stdout, result.exit_code

    def _get_sandbox(self, voyage_id: uuid.UUID) -> str:
        if voyage_id not in self._repos:
            raise GitError("REPO_NOT_CLONED")
        return self._repos[voyage_id]

    async def clone_repo(
        self, voyage_id: uuid.UUID, user_id: uuid.UUID, repo_url: str
    ) -> GitRepoInfo:
        if voyage_id in self._repos:
            raise GitError("REPO_ALREADY_CLONED")

        allowed = getattr(self._settings, "git_allowed_hosts", None)
        allowed_hosts = frozenset(allowed) if allowed else ALLOWED_GIT_HOSTS
        _validate_repo_host(repo_url, allowed_hosts)

        sandbox_id = await self._backend.create(user_id)

        try:
            token = self._settings.github_api_token
            auth_url = _inject_token(repo_url, token) if token else repo_url

            await self._run(sandbox_id, f"git clone {shlex.quote(auth_url)} {REPO_PATH}")
            author_name = shlex.quote(self._settings.git_author_name)
            author_email = shlex.quote(self._settings.git_author_email)
            await self._run(
                sandbox_id,
                f"cd {REPO_PATH} && git config user.name {author_name}"
                f" && git config user.email {author_email}",
            )
        except (GitError, Exception):
            # Rollback: destroy sandbox so retry doesn't hit REPO_ALREADY_CLONED
            try:
                await self._backend.destroy(sandbox_id)
            except Exception:
                logger.warning("Failed to destroy sandbox %s during clone rollback", sandbox_id)
            raise

        self._repos[voyage_id] = sandbox_id
        self._repo_urls[voyage_id] = repo_url

        return GitRepoInfo(
            sandbox_id=sandbox_id,
            repo_url=repo_url,
            default_branch=self._settings.git_default_branch,
        )

    async def create_branch(
        self,
        voyage_id: uuid.UUID,
        user_id: uuid.UUID,
        crew_member: str,
        base_branch: str,
    ) -> GitBranchInfo:
        _validate_branch_component(crew_member)
        sandbox_id = self._get_sandbox(voyage_id)
        branch = _branch_name(crew_member, voyage_id)

        await self._run(
            sandbox_id,
            f"cd {REPO_PATH} && git fetch origin"
            f" && git checkout -b {shlex.quote(branch)}"
            f" origin/{shlex.quote(base_branch)}",
        )

        return GitBranchInfo(name=branch, is_current=True)

    async def list_branches(self, voyage_id: uuid.UUID, user_id: uuid.UUID) -> list[GitBranchInfo]:
        sandbox_id = self._get_sandbox(voyage_id)

        stdout = await self._run(
            sandbox_id,
            f"cd {REPO_PATH} && git branch --format='%(refname:short) %(HEAD)'",
        )

        branches: list[GitBranchInfo] = []
        for line in stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            is_current = line.endswith("*")
            name = line.rstrip(" *").strip()
            branches.append(GitBranchInfo(name=name, is_current=is_current))

        return branches

    async def commit(
        self,
        voyage_id: uuid.UUID,
        user_id: uuid.UUID,
        message: str,
        crew_member: str,
        files: dict[str, str] | None = None,
    ) -> GitCommitInfo:
        sandbox_id = self._get_sandbox(voyage_id)

        if files:
            # put_archive targets /workspace, so prefix paths with repo/
            prefixed = {f"repo/{path}": content for path, content in files.items()}
            await self._backend.execute(
                sandbox_id,
                ExecutionRequest(
                    command=f"cd {REPO_PATH} && echo 'files injected'",
                    files=prefixed,
                ),
            )

        author = f"{crew_member} <{crew_member}@grandline.dev>"
        await self._run(
            sandbox_id,
            f"cd {REPO_PATH} && git add -A"
            f" && git commit -m {shlex.quote(message)} --author={shlex.quote(author)}",
        )

        stdout = await self._run(
            sandbox_id,
            f"cd {REPO_PATH} && git log -1 --format='%H %h %aI'",
        )
        parts = stdout.strip().split(" ", 2)
        sha = parts[0]
        short_sha = parts[1] if len(parts) > 1 else sha[:7]
        timestamp = parts[2] if len(parts) > 2 else ""

        return GitCommitInfo(
            sha=sha,
            short_sha=short_sha,
            message=message,
            author=crew_member,
            timestamp=timestamp,
        )

    async def push(self, voyage_id: uuid.UUID, user_id: uuid.UUID, branch: str) -> GitPushInfo:
        _validate_branch_component(branch)
        sandbox_id = self._get_sandbox(voyage_id)

        await self._run(
            sandbox_id,
            f"cd {REPO_PATH} && git push origin {shlex.quote(branch)}",
        )

        return GitPushInfo(branch=branch, pushed=True)

    async def create_pr(
        self,
        voyage_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> GitPRInfo:
        repo_url = self._repo_urls.get(voyage_id)
        if not repo_url:
            raise GitError("REPO_NOT_CLONED")

        owner_repo = _parse_owner_repo(repo_url)
        token = self._settings.github_api_token

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.github.com/repos/{owner_repo}/pulls",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                json={
                    "title": title,
                    "body": body,
                    "head": head,
                    "base": base,
                },
            )

        if resp.status_code not in (200, 201):
            raise GitError(f"GITHUB_API_ERROR: {resp.status_code} {resp.text}")

        data = resp.json()
        return GitPRInfo(
            number=data["number"],
            url=data["html_url"],
            title=data["title"],
            head=data["head"]["ref"],
            base=data["base"]["ref"],
        )

    async def get_log(
        self,
        voyage_id: uuid.UUID,
        user_id: uuid.UUID,
        branch: str,
        limit: int = 20,
    ) -> list[GitCommitInfo]:
        _validate_branch_component(branch)
        sandbox_id = self._get_sandbox(voyage_id)

        stdout = await self._run(
            sandbox_id,
            f"cd {REPO_PATH} && git log {shlex.quote(branch)}"
            f" -{limit} --format='%H%x00%h%x00%s%x00%an%x00%aI'",
        )

        entries: list[GitCommitInfo] = []
        for line in stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\x00", 4)
            if len(parts) < 5:
                continue
            entries.append(
                GitCommitInfo(
                    sha=parts[0],
                    short_sha=parts[1],
                    message=parts[2],
                    author=parts[3],
                    timestamp=parts[4],
                )
            )

        return entries

    async def check_conflicts(
        self,
        voyage_id: uuid.UUID,
        user_id: uuid.UUID,
        branch: str,
        target: str,
    ) -> GitConflictInfo:
        _validate_branch_component(branch)
        _validate_branch_component(target)
        sandbox_id = self._get_sandbox(voyage_id)

        await self._run(sandbox_id, f"cd {REPO_PATH} && git fetch origin")
        await self._run(sandbox_id, f"cd {REPO_PATH} && git checkout {shlex.quote(branch)}")

        merge_out, exit_code = await self._run_unchecked(
            sandbox_id,
            f"cd {REPO_PATH}"
            f" && git merge --no-commit --no-ff origin/{shlex.quote(target)} 2>&1"
            f'; echo "EXIT:$?"',
        )

        has_conflicts = "EXIT:0" not in merge_out
        conflicting_files: list[str] = []

        if has_conflicts:
            diff_out = await self._run(
                sandbox_id,
                f"cd {REPO_PATH} && git diff --name-only --diff-filter=U",
            )
            conflicting_files = [f.strip() for f in diff_out.strip().splitlines() if f.strip()]

        # Always abort the merge attempt
        await self._run_unchecked(sandbox_id, f"cd {REPO_PATH} && git merge --abort")

        return GitConflictInfo(
            has_conflicts=has_conflicts,
            conflicting_files=conflicting_files,
        )

    async def cleanup_branches(self, voyage_id: uuid.UUID, user_id: uuid.UUID) -> None:
        sandbox_id = self._repos.pop(voyage_id, None)
        self._repo_urls.pop(voyage_id, None)
        if sandbox_id:
            await self._backend.destroy(sandbox_id)

    async def cleanup_all(self) -> None:
        for voyage_id, sandbox_id in list(self._repos.items()):
            try:
                await self._backend.destroy(sandbox_id)
            except Exception:
                logger.warning(
                    "Failed to destroy git sandbox %s for voyage %s",
                    sandbox_id,
                    voyage_id,
                )
        self._repos.clear()
        self._repo_urls.clear()
