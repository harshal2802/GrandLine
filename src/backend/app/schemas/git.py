"""Schemas for Git Integration Service."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class GitCloneRequest(BaseModel):
    repo_url: str | None = None

    @field_validator("repo_url")
    @classmethod
    def validate_https_url(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith("https://"):
            raise ValueError("Only HTTPS URLs are allowed")
        return v


class GitBranchRequest(BaseModel):
    crew_member: str
    base_branch: str = "main"


class GitCommitRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    crew_member: str
    files: dict[str, str] = Field(default_factory=dict)


class GitPushRequest(BaseModel):
    branch: str


class GitPRRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    body: str = ""
    head_branch: str
    base_branch: str = "main"


class GitConflictCheckRequest(BaseModel):
    branch: str
    target_branch: str = "main"


# --- Response schemas ---


class GitRepoInfo(BaseModel):
    sandbox_id: str
    repo_url: str
    default_branch: str


class GitBranchInfo(BaseModel):
    name: str
    is_current: bool


class GitCommitInfo(BaseModel):
    sha: str
    short_sha: str
    message: str
    author: str
    timestamp: str


class GitPushInfo(BaseModel):
    branch: str
    pushed: bool


class GitPRInfo(BaseModel):
    number: int
    url: str
    title: str
    head: str
    base: str


class GitConflictInfo(BaseModel):
    has_conflicts: bool
    conflicting_files: list[str] = Field(default_factory=list)
