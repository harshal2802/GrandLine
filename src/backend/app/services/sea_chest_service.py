"""SeaChestService — store, reveal, and manage encrypted per-user credentials.

The Sea Chest (Phase 0a) is the per-user credential vault. This service owns
owner-scoped CRUD over :class:`UserCredential` rows plus the crypto edge:

- ``store`` encrypts a secret and upserts the ``(user_id, kind)`` row. It returns
  STATUS only (:class:`CredentialStatus`) — never the secret.
- ``reveal`` decrypts the secret for INTERNAL consumers (the Cabin/adapters in
  later phases). It is NOT for API responses — see its docstring.
- ``status`` / ``status_for`` expose what the user has connected, secret-free.
- ``delete`` removes a credential.

Every operation is owner-scoped by ``user_id`` so a user can only touch their own
credentials. No secret (plaintext or ciphertext) is ever logged.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.seachest_crypto import decrypt, encrypt
from app.models.user_credential import UserCredential
from app.schemas.sea_chest import CredentialStatus


class SeaChestError(Exception):
    """Raised when a Sea Chest operation fails (e.g. not found / not owned)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class SeaChestService:
    """Encrypted per-user credential storage, owner-scoped throughout."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    @classmethod
    def reader(cls, session: AsyncSession, settings: Settings) -> SeaChestService:
        """Create a session-only instance (mirrors other services' ``reader``)."""
        return cls(session, settings)

    async def _get_row(self, user_id: uuid.UUID, kind: str) -> UserCredential | None:
        """Fetch the owned credential row for ``(user_id, kind)`` or ``None``.

        Owner-scoping is in the query so a foreign credential is indistinguishable
        from a missing one (no existence leak).
        """
        result = await self._session.execute(
            select(UserCredential).where(
                UserCredential.user_id == user_id,
                UserCredential.kind == kind,
            )
        )
        return result.scalar_one_or_none()

    async def store(
        self,
        user_id: uuid.UUID,
        kind: str,
        secret: str,
        *,
        label: str | None = None,
    ) -> CredentialStatus:
        """Encrypt ``secret`` and upsert the ``(user_id, kind)`` credential.

        Returns STATUS only — never the secret or ciphertext. Connecting a kind the
        user already has replaces its ciphertext and label in place.
        """
        ciphertext = encrypt(secret, cfg=self._settings)

        row = await self._get_row(user_id, kind)
        if row is None:
            row = UserCredential(
                id=uuid.uuid4(),
                user_id=user_id,
                kind=kind,
                ciphertext=ciphertext,
                label=label,
            )
            self._session.add(row)
        else:
            row.ciphertext = ciphertext
            row.label = label

        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(row)
        return self._to_status(row)

    async def reveal(self, user_id: uuid.UUID, kind: str) -> str | None:
        """Decrypt and return the owned credential's secret — INTERNAL USE ONLY.

        This returns PLAINTEXT and must NEVER feed an API response. It exists for
        internal consumers (the Cabin / provider adapters in later phases) that
        need the real secret. Returns ``None`` when the user has not connected this
        kind. Updates ``last_used_at`` to mark the access.
        """
        row = await self._get_row(user_id, kind)
        if row is None:
            return None

        secret = decrypt(row.ciphertext, cfg=self._settings)
        row.last_used_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.commit()
        return secret

    async def status(self, user_id: uuid.UUID) -> list[CredentialStatus]:
        """Return the STATUS of every credential the user has connected."""
        result = await self._session.execute(
            select(UserCredential)
            .where(UserCredential.user_id == user_id)
            .order_by(UserCredential.kind)
        )
        return [self._to_status(row) for row in result.scalars().all()]

    async def status_for(self, user_id: uuid.UUID, kind: str) -> CredentialStatus | None:
        """Return one credential's STATUS, or ``None`` if not connected."""
        row = await self._get_row(user_id, kind)
        if row is None:
            return None
        return self._to_status(row)

    async def delete(self, user_id: uuid.UUID, kind: str) -> None:
        """Delete the owned credential, or raise ``NOT_FOUND`` if not connected."""
        row = await self._get_row(user_id, kind)
        if row is None:
            raise SeaChestError("NOT_FOUND", "Credential not found")
        await self._session.delete(row)
        await self._session.commit()

    @staticmethod
    def _to_status(row: UserCredential) -> CredentialStatus:
        """Map a row to a secret-free :class:`CredentialStatus` (connected=True)."""
        return CredentialStatus(
            kind=row.kind,
            connected=True,
            label=row.label,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
        )
