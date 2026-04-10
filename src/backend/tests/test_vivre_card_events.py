"""Tests for CheckpointCreatedEvent integration with Den Den Mushi event system."""

from __future__ import annotations

import json
import uuid

import pytest
from pydantic import ValidationError

from app.den_den_mushi.events import (
    CheckpointCreatedEvent,
    parse_event,
)
from app.models.enums import CrewRole

VOYAGE_ID = uuid.uuid4()


class TestCheckpointCreatedEvent:
    def test_event_type_is_checkpoint_created(self) -> None:
        event = CheckpointCreatedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.CAPTAIN,
            payload={
                "card_id": str(uuid.uuid4()),
                "crew_member": "captain",
                "reason": "interval",
            },
        )
        assert event.event_type == "checkpoint_created"

    def test_event_serializes_to_json(self) -> None:
        event = CheckpointCreatedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.NAVIGATOR,
            payload={
                "card_id": str(uuid.uuid4()),
                "crew_member": "navigator",
                "reason": "failover",
            },
        )
        json_str = event.model_dump_json()
        data = json.loads(json_str)
        assert data["event_type"] == "checkpoint_created"
        assert data["source_role"] == "navigator"

    def test_event_round_trips_through_parse(self) -> None:
        event = CheckpointCreatedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.DOCTOR,
            payload={
                "card_id": str(uuid.uuid4()),
                "crew_member": "doctor",
                "reason": "pause",
            },
        )
        json_str = event.model_dump_json()
        restored = parse_event(json.loads(json_str))
        assert isinstance(restored, CheckpointCreatedEvent)
        assert restored.event_id == event.event_id
        assert restored.voyage_id == event.voyage_id
        assert restored.payload == event.payload

    def test_parse_event_recognizes_checkpoint_created(self) -> None:
        data = {
            "event_type": "checkpoint_created",
            "voyage_id": str(VOYAGE_ID),
            "source_role": "captain",
            "payload": {
                "card_id": str(uuid.uuid4()),
                "crew_member": "captain",
                "reason": "migration",
            },
        }
        event = parse_event(data)
        assert isinstance(event, CheckpointCreatedEvent)

    def test_event_is_immutable(self) -> None:
        event = CheckpointCreatedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.CAPTAIN,
            payload={},
        )
        with pytest.raises(ValidationError):
            event.voyage_id = uuid.uuid4()  # type: ignore[misc]
