"""Schemas for per-user integrations — GitHub device-code OAuth (Phase A3) +
Claude Code device-login in the Cabin (Phase C0).

SECURITY: NO schema here ever carries the access token outbound. ``DeviceFlowStart``
returns the transient ``device_code``/``user_code`` for the client round-trip;
``DeviceFlowStatus`` carries ONLY the GitHub ``login`` on success — the token lives
solely in the Sea Chest. Likewise the Claude schemas (``ClaudeLoginStart`` /
``ClaudeLoginStatus``) carry only the verification URL / opaque ``login_id`` and a
``connected``/``pending``/``error`` status — never the captured ``CLAUDE_CODE_OAUTH_TOKEN``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DeviceFlowStart(BaseModel):
    """The device-flow handshake to SHOW the user + poll with.

    ``user_code`` + ``verification_uri`` are presented to the user; ``device_code``
    is the opaque handle the client polls ``/device/poll`` with. No access token —
    there isn't one yet.
    """

    model_config = ConfigDict(extra="forbid")

    user_code: str
    verification_uri: str
    device_code: str
    interval: int
    expires_in: int


class DeviceFlowPollRequest(BaseModel):
    """Poll body: the ``device_code`` returned by ``/device/start``."""

    model_config = ConfigDict(extra="forbid")

    device_code: str = Field(min_length=1)


class DeviceFlowStatus(BaseModel):
    """The outcome of a poll — NEVER carries the access token.

    ``connected`` carries only the GitHub ``login`` (the token is in the Sea Chest);
    ``pending`` means the user hasn't approved yet; ``error`` carries the GitHub
    error code (e.g. ``expired_token``/``access_denied``).
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "connected", "error"]
    login: str | None = None
    error: str | None = None


class ClaudeLoginStart(BaseModel):
    """The Claude Code device-login handshake to SHOW the user + poll with (C0).

    The Claude CLI's login/`setup-token` flow (run INSIDE the user's Cabin) prints a
    ``verification_uri`` the user opens to approve, optionally a short ``user_code``,
    and an opaque ``login_id`` the client polls ``/claude/login/poll`` with. No token
    — there isn't one until the user approves and the poll captures it into the Sea
    Chest.
    """

    model_config = ConfigDict(extra="forbid")

    verification_uri: str
    user_code: str | None = None
    login_id: str


class ClaudeLoginPollRequest(BaseModel):
    """Poll body: the ``login_id`` returned by ``/claude/login/start``."""

    model_config = ConfigDict(extra="forbid")

    login_id: str = Field(min_length=1)


class ClaudeLoginStatus(BaseModel):
    """The outcome of a Claude login poll — NEVER carries the OAuth token (C0).

    ``connected`` means the token was captured and vaulted in the Sea Chest
    (``kind="claude_code"``); ``pending`` means the user hasn't approved yet;
    ``error`` carries a short error code. The captured ``CLAUDE_CODE_OAUTH_TOKEN``
    never appears in any field — it lives solely in the Sea Chest.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "connected", "error"]
    label: str | None = None
    error: str | None = None


__all__ = [
    "ClaudeLoginPollRequest",
    "ClaudeLoginStart",
    "ClaudeLoginStatus",
    "DeviceFlowPollRequest",
    "DeviceFlowStart",
    "DeviceFlowStatus",
]
