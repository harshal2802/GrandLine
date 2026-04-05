"""Tests for Den Den Mushi event schemas and parse_event discriminated union."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.den_den_mushi.events import (
    CodeGeneratedEvent,
    DenDenMushiEvent,
    DeploymentCompletedEvent,
    HealthCheckWrittenEvent,
    PoneglyphDraftedEvent,
    ProviderSwitchedEvent,
    ValidationPassedEvent,
    VoyagePlanCreatedEvent,
    parse_event,
)
from app.models.enums import CrewRole

VOYAGE_ID = uuid.uuid4()


class TestDenDenMushiEventBase:
    def test_event_id_auto_generated(self) -> None:
        event = VoyagePlanCreatedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.CAPTAIN,
            payload={"plan_id": str(uuid.uuid4()), "phase_count": 5},
        )
        assert isinstance(event.event_id, uuid.UUID)

    def test_timestamp_auto_generated(self) -> None:
        before = datetime.now(UTC)
        event = VoyagePlanCreatedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.CAPTAIN,
            payload={"plan_id": str(uuid.uuid4()), "phase_count": 5},
        )
        after = datetime.now(UTC)
        assert before <= event.timestamp <= after

    def test_event_is_immutable(self) -> None:
        event = VoyagePlanCreatedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.CAPTAIN,
            payload={"plan_id": str(uuid.uuid4()), "phase_count": 5},
        )
        with pytest.raises(ValidationError):
            event.voyage_id = uuid.uuid4()  # type: ignore[misc]

    def test_two_events_have_different_ids(self) -> None:
        kwargs = dict(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.CAPTAIN,
            payload={"plan_id": str(uuid.uuid4()), "phase_count": 5},
        )
        e1 = VoyagePlanCreatedEvent(**kwargs)
        e2 = VoyagePlanCreatedEvent(**kwargs)
        assert e1.event_id != e2.event_id


class TestConcreteEventTypes:
    def test_voyage_plan_created(self) -> None:
        event = VoyagePlanCreatedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.CAPTAIN,
            payload={"plan_id": str(uuid.uuid4()), "phase_count": 5},
        )
        assert event.event_type == "voyage_plan_created"

    def test_poneglyph_drafted(self) -> None:
        event = PoneglyphDraftedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.NAVIGATOR,
            payload={"poneglyph_id": str(uuid.uuid4()), "phase_number": 1},
        )
        assert event.event_type == "poneglyph_drafted"

    def test_health_check_written(self) -> None:
        event = HealthCheckWrittenEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.DOCTOR,
            payload={"test_count": 12, "phase_number": 1},
        )
        assert event.event_type == "health_check_written"

    def test_code_generated(self) -> None:
        event = CodeGeneratedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.SHIPWRIGHT,
            payload={"files": ["main.py", "utils.py"], "phase_number": 1},
        )
        assert event.event_type == "code_generated"

    def test_validation_passed(self) -> None:
        event = ValidationPassedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.DOCTOR,
            payload={"tests_passed": 10, "tests_total": 10},
        )
        assert event.event_type == "validation_passed"

    def test_deployment_completed(self) -> None:
        event = DeploymentCompletedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.HELMSMAN,
            payload={"tier": "preview", "url": "https://preview.example.com"},
        )
        assert event.event_type == "deployment_completed"

    def test_provider_switched(self) -> None:
        event = ProviderSwitchedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.CAPTAIN,
            payload={
                "old_provider": "openai",
                "new_provider": "anthropic",
                "role": "navigator",
            },
        )
        assert event.event_type == "provider_switched"


class TestParseEvent:
    def test_parse_voyage_plan_created(self) -> None:
        data = {
            "event_type": "voyage_plan_created",
            "voyage_id": str(VOYAGE_ID),
            "source_role": "captain",
            "payload": {"plan_id": str(uuid.uuid4()), "phase_count": 5},
        }
        event = parse_event(data)
        assert isinstance(event, VoyagePlanCreatedEvent)

    def test_parse_each_event_type(self) -> None:
        types_and_classes = [
            ("voyage_plan_created", VoyagePlanCreatedEvent),
            ("poneglyph_drafted", PoneglyphDraftedEvent),
            ("health_check_written", HealthCheckWrittenEvent),
            ("code_generated", CodeGeneratedEvent),
            ("validation_passed", ValidationPassedEvent),
            ("deployment_completed", DeploymentCompletedEvent),
            ("provider_switched", ProviderSwitchedEvent),
        ]
        for event_type, expected_class in types_and_classes:
            data = {
                "event_type": event_type,
                "voyage_id": str(VOYAGE_ID),
                "source_role": "captain",
                "payload": {},
            }
            event = parse_event(data)
            assert isinstance(event, expected_class), f"Failed for {event_type}"

    def test_parse_unknown_event_type_raises(self) -> None:
        data = {
            "event_type": "unknown_event",
            "voyage_id": str(VOYAGE_ID),
            "source_role": "captain",
            "payload": {},
        }
        with pytest.raises(ValidationError):
            parse_event(data)

    def test_parse_missing_required_field_raises(self) -> None:
        data = {
            "event_type": "voyage_plan_created",
            # missing voyage_id
            "source_role": "captain",
            "payload": {},
        }
        with pytest.raises(ValidationError):
            parse_event(data)

    def test_parse_invalid_source_role_raises(self) -> None:
        data = {
            "event_type": "voyage_plan_created",
            "voyage_id": str(VOYAGE_ID),
            "source_role": "pirate_king",
            "payload": {},
        }
        with pytest.raises(ValidationError):
            parse_event(data)

    def test_json_round_trip(self) -> None:
        event = VoyagePlanCreatedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.CAPTAIN,
            payload={"plan_id": str(uuid.uuid4()), "phase_count": 5},
        )
        json_str = event.model_dump_json()
        restored = parse_event(json.loads(json_str))
        assert isinstance(restored, VoyagePlanCreatedEvent)
        assert restored.event_id == event.event_id
        assert restored.voyage_id == event.voyage_id
        assert restored.payload == event.payload

    def test_all_event_types_round_trip(self) -> None:
        events: list[DenDenMushiEvent] = [
            VoyagePlanCreatedEvent(voyage_id=VOYAGE_ID, source_role=CrewRole.CAPTAIN, payload={}),
            PoneglyphDraftedEvent(voyage_id=VOYAGE_ID, source_role=CrewRole.NAVIGATOR, payload={}),
            HealthCheckWrittenEvent(voyage_id=VOYAGE_ID, source_role=CrewRole.DOCTOR, payload={}),
            CodeGeneratedEvent(voyage_id=VOYAGE_ID, source_role=CrewRole.SHIPWRIGHT, payload={}),
            ValidationPassedEvent(voyage_id=VOYAGE_ID, source_role=CrewRole.DOCTOR, payload={}),
            DeploymentCompletedEvent(
                voyage_id=VOYAGE_ID, source_role=CrewRole.HELMSMAN, payload={}
            ),
            ProviderSwitchedEvent(voyage_id=VOYAGE_ID, source_role=CrewRole.CAPTAIN, payload={}),
        ]
        for event in events:
            json_str = event.model_dump_json()
            restored = parse_event(json.loads(json_str))
            assert type(restored) is type(event)
            assert restored.event_id == event.event_id
