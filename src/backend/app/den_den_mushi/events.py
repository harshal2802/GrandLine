from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.models.enums import CrewRole


class DenDenMushiEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: str
    voyage_id: uuid.UUID
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_role: CrewRole
    payload: dict[str, Any] = Field(default_factory=dict)


class VoyagePlanCreatedEvent(DenDenMushiEvent):
    event_type: Literal["voyage_plan_created"] = "voyage_plan_created"


class PoneglyphDraftedEvent(DenDenMushiEvent):
    event_type: Literal["poneglyph_drafted"] = "poneglyph_drafted"


class HealthCheckWrittenEvent(DenDenMushiEvent):
    event_type: Literal["health_check_written"] = "health_check_written"


class CodeGeneratedEvent(DenDenMushiEvent):
    event_type: Literal["code_generated"] = "code_generated"


class TestsPassedEvent(DenDenMushiEvent):
    event_type: Literal["tests_passed"] = "tests_passed"


class ValidationPassedEvent(DenDenMushiEvent):
    event_type: Literal["validation_passed"] = "validation_passed"


class ValidationFailedEvent(DenDenMushiEvent):
    event_type: Literal["validation_failed"] = "validation_failed"


class DeploymentCompletedEvent(DenDenMushiEvent):
    event_type: Literal["deployment_completed"] = "deployment_completed"


class ProviderSwitchedEvent(DenDenMushiEvent):
    event_type: Literal["provider_switched"] = "provider_switched"


class CheckpointCreatedEvent(DenDenMushiEvent):
    event_type: Literal["checkpoint_created"] = "checkpoint_created"


AnyEvent = Annotated[
    VoyagePlanCreatedEvent
    | PoneglyphDraftedEvent
    | HealthCheckWrittenEvent
    | CodeGeneratedEvent
    | TestsPassedEvent
    | ValidationPassedEvent
    | ValidationFailedEvent
    | DeploymentCompletedEvent
    | ProviderSwitchedEvent
    | CheckpointCreatedEvent,
    Field(discriminator="event_type"),
]

_event_adapter: TypeAdapter[AnyEvent] = TypeAdapter(AnyEvent)


def parse_event(data: dict[str, Any]) -> AnyEvent:
    return _event_adapter.validate_python(data)
