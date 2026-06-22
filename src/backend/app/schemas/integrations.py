"""Schemas for per-user integrations — GitHub device-code OAuth (Phase A3).

SECURITY: NO schema here ever carries the access token outbound. ``DeviceFlowStart``
returns the transient ``device_code``/``user_code`` for the client round-trip;
``DeviceFlowStatus`` carries ONLY the GitHub ``login`` on success — the token lives
solely in the Sea Chest.
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


__all__ = ["DeviceFlowPollRequest", "DeviceFlowStart", "DeviceFlowStatus"]
