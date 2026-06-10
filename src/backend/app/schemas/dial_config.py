import logging
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)

# Providers the Dial System can build adapters for (mirrors factory.create_adapter).
SUPPORTED_PROVIDERS = frozenset(
    {"anthropic", "openai", "ollama", "claude_code", "claude-code"}
)


def validate_fallback_chain(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate the shape of a ``fallback_chain`` mapping.

    Each role maps to a list of entries; an entry is either a bare provider
    string or a ``{"provider": ..., "model": ...}`` object. The provider must be
    supported. Model strings can't be validated against a provider's catalog, so
    only the shape and provider name are checked here.
    """
    if value is None:
        return value
    for role, entries in value.items():
        if not isinstance(entries, list):
            raise ValueError(f"fallback_chain[{role!r}] must be a list of providers")
        for entry in entries:
            provider: str | None
            if isinstance(entry, str):
                provider = entry
            elif isinstance(entry, dict):
                provider = entry.get("provider")
                if not provider:
                    raise ValueError(
                        f"fallback_chain[{role!r}] entry missing 'provider': {entry!r}"
                    )
            else:
                raise ValueError(
                    f"fallback_chain[{role!r}] entry must be a provider string or "
                    f"a {{'provider', 'model'}} object, got: {entry!r}"
                )
            if provider not in SUPPORTED_PROVIDERS:
                raise ValueError(
                    f"Unsupported provider {provider!r} in fallback_chain[{role!r}]; "
                    f"choose one of {sorted(SUPPORTED_PROVIDERS)}"
                )
    return value


class DialConfigCreate(BaseModel):
    voyage_id: uuid.UUID
    role_mapping: dict[str, Any]
    fallback_chain: dict[str, Any] | None = None

    @field_validator("fallback_chain")
    @classmethod
    def _check_fallback_chain(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_fallback_chain(v)


class DialConfigUpdate(BaseModel):
    role_mapping: dict[str, Any] | None = None
    fallback_chain: dict[str, Any] | None = None

    @field_validator("fallback_chain")
    @classmethod
    def _check_fallback_chain(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_fallback_chain(v)


class DialConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    voyage_id: uuid.UUID
    role_mapping: dict[str, Any]
    fallback_chain: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class ShipwrightRoleConfig(BaseModel):
    model_config = ConfigDict(strict=True)

    max_concurrency: int | None = Field(default=None, ge=1, le=10)


def resolve_shipwright_max_concurrency(role_mapping: dict[str, Any] | None) -> int:
    """Return a safe concurrency bound for the Shipwright role.

    Falls back to 1 on any invalid, missing, or non-dict shape so the caller
    can trust the return without defensive checks.
    """
    if not role_mapping:
        return 1
    raw = role_mapping.get("shipwright")
    if not isinstance(raw, dict):
        return 1
    try:
        cfg = ShipwrightRoleConfig.model_validate(raw)
    except ValidationError:
        logger.warning(
            "Invalid shipwright role config — falling back to max_concurrency=1: %r", raw
        )
        return 1
    return cfg.max_concurrency or 1
