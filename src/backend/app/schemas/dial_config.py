import logging
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


class DialConfigCreate(BaseModel):
    voyage_id: uuid.UUID
    role_mapping: dict[str, Any]
    fallback_chain: dict[str, Any] | None = None


class DialConfigUpdate(BaseModel):
    role_mapping: dict[str, Any] | None = None
    fallback_chain: dict[str, Any] | None = None


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
