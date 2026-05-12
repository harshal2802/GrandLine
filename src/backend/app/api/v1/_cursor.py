"""Opaque base64url cursor helper used by paginated list endpoints.

Both the voyages list (P7) and crew-actions list (P6) page on a
``(timestamp, id)`` tuple. The cursor encodes that tuple as
``base64url(JSON.stringify({"ts": iso8601, "id": uuid_str}))``. Frontend
treats the cursor as opaque.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from datetime import datetime


class CursorError(ValueError):
    """Raised when a supplied cursor cannot be decoded."""


@dataclass(frozen=True)
class Cursor:
    """Decoded pagination cursor.

    Stable round-trip: ``decode(encode(c)) == c``.
    """

    ts: datetime
    id: uuid.UUID


def encode_cursor(ts: datetime, row_id: uuid.UUID) -> str:
    """Serialize a (timestamp, id) into an opaque base64url string."""
    payload = json.dumps({"ts": ts.isoformat(), "id": str(row_id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(raw: str) -> Cursor:
    """Decode an opaque cursor; raise CursorError on malformed input."""
    if not raw:
        raise CursorError("empty cursor")

    # base64.urlsafe_b64decode requires padding; we strip it on encode for
    # URL aesthetics, so reapply here.
    pad_len = (-len(raw)) % 4
    padded = raw + ("=" * pad_len)

    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (binascii.Error, ValueError) as exc:
        raise CursorError(f"invalid base64url cursor: {exc}") from exc

    try:
        obj = json.loads(decoded.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CursorError(f"cursor is not valid JSON: {exc}") from exc

    if not isinstance(obj, dict) or "ts" not in obj or "id" not in obj:
        raise CursorError("cursor missing required fields")

    try:
        ts = datetime.fromisoformat(obj["ts"])
    except (TypeError, ValueError) as exc:
        raise CursorError(f"invalid cursor timestamp: {exc}") from exc

    try:
        row_id = uuid.UUID(obj["id"])
    except (TypeError, ValueError, AttributeError) as exc:
        raise CursorError(f"invalid cursor id: {exc}") from exc

    return Cursor(ts=ts, id=row_id)


__all__ = [
    "Cursor",
    "CursorError",
    "decode_cursor",
    "encode_cursor",
]
