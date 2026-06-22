"""Schemas for Standing Orders — reusable voyage templates / presets."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.dial_config import validate_fallback_chain


def _validate_dial_config_bundle(
    value: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Light validation of a ``{role_mapping, fallback_chain}`` preset bundle.

    A Standing Order's ``dial_config`` is the bundle later seeded into a charted
    voyage's ``DialConfig``. We only check the shape here — ``role_mapping`` must
    be a dict, and ``fallback_chain`` reuses the Dial System's own validator so
    the preset can't encode an unsupported provider.
    """
    if value is None:
        return value
    role_mapping = value.get("role_mapping")
    if role_mapping is not None and not isinstance(role_mapping, dict):
        raise ValueError("dial_config.role_mapping must be a mapping of role -> provider config")
    validate_fallback_chain(value.get("fallback_chain"))
    return value


class StandingOrderCreate(BaseModel):
    """Payload for creating a new Standing Order (a reusable voyage preset)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    target_repo: str | None = Field(default=None, max_length=500)
    dial_config: dict[str, Any] | None = None
    plan_skeleton: dict[str, Any] | None = None
    injected_context: str | None = None

    @field_validator("dial_config")
    @classmethod
    def _check_dial_config(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_dial_config_bundle(v)


class StandingOrderUpdate(BaseModel):
    """Partial update — every field is optional (PATCH semantics)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    target_repo: str | None = Field(default=None, max_length=500)
    dial_config: dict[str, Any] | None = None
    plan_skeleton: dict[str, Any] | None = None
    injected_context: str | None = None

    @field_validator("dial_config")
    @classmethod
    def _check_dial_config(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_dial_config_bundle(v)


class StandingOrderRead(BaseModel):
    """A Standing Order as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: str | None
    target_repo: str | None
    dial_config: dict[str, Any] | None
    plan_skeleton: dict[str, Any] | None
    injected_context: str | None
    created_at: datetime
    updated_at: datetime


class ChartFromStandingOrderRequest(BaseModel):
    """Chart a voyage from a Standing Order, with optional per-chart overrides."""

    model_config = ConfigDict(extra="forbid")

    task: str = Field(min_length=10, max_length=5000)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    target_repo: str | None = Field(default=None, max_length=500)
