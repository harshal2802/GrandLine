from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import CrewRole


class ProviderConfig(BaseModel):
    provider: str
    model: str
    max_tokens: int = 4096


class CompletionRequest(BaseModel):
    messages: list[dict[str, str]]
    role: CrewRole
    voyage_id: uuid.UUID | None = None
    max_tokens: int = 4096
    temperature: float = 1.0
    extra: dict[str, Any] = Field(default_factory=dict)


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class CompletionResult(BaseModel):
    content: str
    provider: str
    model: str
    usage: TokenUsage = Field(default_factory=TokenUsage)


class RateLimitStatus(BaseModel):
    is_limited: bool = False
    remaining_tokens: int | None = None
    remaining_requests: int | None = None
    reset_at: datetime | None = None
