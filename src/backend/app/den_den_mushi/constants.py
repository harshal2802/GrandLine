import uuid

from app.models.enums import CrewRole

STREAM_PREFIX = "grandline:events"
DEAD_LETTER_STREAM = f"{STREAM_PREFIX}:dead_letter"
BROADCAST_STREAM = f"{STREAM_PREFIX}:broadcast"

MAX_RETRIES = 3
CLAIM_MIN_IDLE_MS = 30_000  # 30 seconds
BLOCK_MS = 5_000  # blocking read timeout


def stream_key(voyage_id: uuid.UUID) -> str:
    return f"{STREAM_PREFIX}:{voyage_id}"


def group_name(role: CrewRole) -> str:
    return f"crew:{role.value}"
