"""Git Integration REST API endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.v1.dependencies import get_authorized_voyage, get_current_user, get_git_service
from app.models.user import User
from app.models.voyage import Voyage
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
from app.services.git_service import GitError, GitService

router = APIRouter(prefix="/voyages/{voyage_id}/git", tags=["git"])


def _handle_git_error(exc: GitError) -> HTTPException:
    msg = str(exc)
    if "REPO_NOT_CLONED" in msg or "REPO_ALREADY_CLONED" in msg:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": msg.split(":")[0].strip(), "message": msg}},
        )
    if "DISALLOWED_HOST" in msg:
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "DISALLOWED_HOST", "message": msg}},
        )
    if "NO_TARGET_REPO" in msg or "INVALID_BRANCH_NAME" in msg:
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": msg.split(":")[0].strip(), "message": msg}},
        )
    if "GITHUB_API_ERROR" in msg:
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "GITHUB_API_ERROR", "message": msg}},
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"error": {"code": "GIT_ERROR", "message": msg}},
    )


@router.post("/clone", response_model=GitRepoInfo, status_code=status.HTTP_201_CREATED)
async def clone_repo(
    voyage_id: uuid.UUID,
    body: GitCloneRequest,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    git_service: GitService = Depends(get_git_service),
) -> GitRepoInfo:
    repo_url = body.repo_url or voyage.target_repo
    if not repo_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "NO_TARGET_REPO",
                    "message": "No repo URL provided and voyage has no target_repo",
                }
            },
        )
    try:
        return await git_service.clone_repo(voyage_id, user.id, repo_url)
    except GitError as exc:
        raise _handle_git_error(exc) from exc


@router.post("/branches", response_model=GitBranchInfo, status_code=status.HTTP_201_CREATED)
async def create_branch(
    voyage_id: uuid.UUID,
    body: GitBranchRequest,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    git_service: GitService = Depends(get_git_service),
) -> GitBranchInfo:
    try:
        return await git_service.create_branch(
            voyage_id, user.id, body.crew_member, body.base_branch
        )
    except GitError as exc:
        raise _handle_git_error(exc) from exc


@router.get("/branches", response_model=list[GitBranchInfo])
async def list_branches(
    voyage_id: uuid.UUID,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    git_service: GitService = Depends(get_git_service),
) -> list[GitBranchInfo]:
    try:
        return await git_service.list_branches(voyage_id, user.id)
    except GitError as exc:
        raise _handle_git_error(exc) from exc


@router.post("/commit", response_model=GitCommitInfo, status_code=status.HTTP_201_CREATED)
async def commit_changes(
    voyage_id: uuid.UUID,
    body: GitCommitRequest,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    git_service: GitService = Depends(get_git_service),
) -> GitCommitInfo:
    try:
        return await git_service.commit(
            voyage_id, user.id, body.message, body.crew_member, body.files or None
        )
    except GitError as exc:
        raise _handle_git_error(exc) from exc


@router.post("/push", response_model=GitPushInfo)
async def push_branch(
    voyage_id: uuid.UUID,
    body: GitPushRequest,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    git_service: GitService = Depends(get_git_service),
) -> GitPushInfo:
    try:
        return await git_service.push(voyage_id, user.id, body.branch)
    except GitError as exc:
        raise _handle_git_error(exc) from exc


@router.post("/pr", response_model=GitPRInfo, status_code=status.HTTP_201_CREATED)
async def create_pull_request(
    voyage_id: uuid.UUID,
    body: GitPRRequest,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    git_service: GitService = Depends(get_git_service),
) -> GitPRInfo:
    try:
        return await git_service.create_pr(
            voyage_id, user.id, body.title, body.body, body.head_branch, body.base_branch
        )
    except GitError as exc:
        raise _handle_git_error(exc) from exc


@router.get("/log", response_model=list[GitCommitInfo])
async def get_log(
    voyage_id: uuid.UUID,
    branch: str = "main",
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    git_service: GitService = Depends(get_git_service),
) -> list[GitCommitInfo]:
    try:
        return await git_service.get_log(voyage_id, user.id, branch, limit)
    except GitError as exc:
        raise _handle_git_error(exc) from exc


@router.post("/conflicts", response_model=GitConflictInfo)
async def check_conflicts(
    voyage_id: uuid.UUID,
    body: GitConflictCheckRequest,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    git_service: GitService = Depends(get_git_service),
) -> GitConflictInfo:
    try:
        return await git_service.check_conflicts(
            voyage_id, user.id, body.branch, body.target_branch
        )
    except GitError as exc:
        raise _handle_git_error(exc) from exc


@router.delete(
    "/branches",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def cleanup_branches(
    voyage_id: uuid.UUID,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    git_service: GitService = Depends(get_git_service),
) -> Response:
    try:
        await git_service.cleanup_branches(voyage_id, user.id)
    except GitError as exc:
        raise _handle_git_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
