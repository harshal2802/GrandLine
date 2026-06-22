"""Schemas for Message in a Bottle — external triggers (GitHub issue webhook).

A real GitHub ``issues`` webhook payload is large; we model only the minimal
subset needed to chart a course and record provenance. Every nested model uses
``extra="ignore"`` so the dozens of unknown fields GitHub sends never break
parsing.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GithubLabel(BaseModel):
    """A single label on a GitHub issue (we only need its name)."""

    model_config = ConfigDict(extra="ignore")

    name: str


class GithubIssue(BaseModel):
    """The issue subset of a GitHub ``issues`` webhook payload."""

    model_config = ConfigDict(extra="ignore")

    number: int
    title: str
    body: str | None = None
    html_url: str
    labels: list[GithubLabel] = Field(default_factory=list)


class GithubRepository(BaseModel):
    """The repository subset of a GitHub ``issues`` webhook payload."""

    model_config = ConfigDict(extra="ignore")

    full_name: str
    clone_url: str | None = None


class GithubSender(BaseModel):
    """The sender subset of a GitHub ``issues`` webhook payload."""

    model_config = ConfigDict(extra="ignore")

    login: str


class GithubIssueWebhook(BaseModel):
    """A minimal, parse-tolerant view of a GitHub ``issues`` webhook event."""

    model_config = ConfigDict(extra="ignore")

    action: str
    issue: GithubIssue
    repository: GithubRepository
    sender: GithubSender


class TriggerResult(BaseModel):
    """The outcome of an inbound trigger: a course was charted, or it was ignored."""

    status: Literal["charted", "ignored"]
    voyage_id: uuid.UUID | None = None
    reason: str | None = None
