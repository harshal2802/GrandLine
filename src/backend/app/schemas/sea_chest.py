"""Schemas for the Sea Chest — the encrypted per-user credential vault.

Critically, NO schema here carries the secret or the ciphertext outbound. The
connect request takes a secret IN; everything the API returns is status only
(``CredentialStatus``) — the secret never leaves the vault over the API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The kinds of credential the Sea Chest can hold. Anything else is rejected at the
# schema boundary. ``claude_code`` powers the C0 device-login adapter; ``github``
# powers A3 per-user git — both INTERNAL consumers of decrypted secrets later.
CredentialKind = Literal["claude_code", "github"]


class SeaChestConnectRequest(BaseModel):
    """Payload for connecting (storing/replacing) a credential of a given kind.

    The ``secret`` is encrypted at rest and is NEVER returned by any endpoint.
    ``label`` is a non-secret hint only (e.g. a token's last-4, or "device-login").
    """

    model_config = ConfigDict(extra="forbid")

    kind: CredentialKind
    secret: str = Field(min_length=1)
    label: str | None = Field(default=None, max_length=255)


class CredentialStatus(BaseModel):
    """A credential's STATUS as returned by the API — never the secret/ciphertext."""

    model_config = ConfigDict(from_attributes=True)

    kind: str
    connected: bool
    label: str | None
    created_at: datetime
    last_used_at: datetime | None
