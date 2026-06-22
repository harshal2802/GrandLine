"""Sea Chest crypto — derive a Fernet key from the env and encrypt/decrypt secrets.

The Sea Chest is the per-user credential vault (Phase 0a). This module is the
crypto edge: it turns the deployment-level ``Settings.seachest_key`` into a valid
Fernet key and exposes ``encrypt``/``decrypt`` over arbitrary string secrets.

Security posture (mirrors ``validate_production_settings`` in ``app/main.py``):

- The key derives from ``settings.seachest_key`` (env ``GRANDLINE_SEACHEST_KEY``).
  It NEVER lives in code or the database.
- In ``debug`` mode, an unset key derives a STABLE dev key (so local dev works) and
  logs a warning — the same value every run, so locally-stored ciphertext stays
  decryptable across restarts.
- In non-debug mode, an unset key raises :class:`SeaChestKeyError` the first time
  encryption is needed (fail closed — never silently use a weak/derived key in
  production).
- No secret (plaintext, ciphertext, or key material) is ever placed in a log line
  or an exception message.

This module is pure and unit-testable: no DB, no I/O beyond reading settings.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)

# Stable, well-known dev seed used ONLY in debug mode when no key is configured.
# It is intentionally fixed (not random) so ciphertext written by a local dev run
# survives a restart. It is NOT a secret and MUST NOT be relied on in production —
# non-debug deployments fail closed instead (see ``_resolve_key``).
_DEV_KEY_SEED = "grandline-seachest-dev-key-do-not-use-in-production"


class SeaChestKeyError(Exception):
    """Raised when the Sea Chest encryption key is missing in a non-debug deploy.

    The message never contains key material — only guidance to configure one.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _derive_fernet_key(raw: str) -> bytes:
    """Turn an arbitrary string into a valid urlsafe-base64 32-byte Fernet key.

    If ``raw`` is already a valid Fernet key, it is accepted as-is. Otherwise a key
    is derived deterministically via SHA-256 → ``urlsafe_b64encode`` so the same
    configured value always yields the same key (ciphertext stays decryptable).
    """
    candidate = raw.encode()
    try:
        # Accept an already-valid Fernet key unchanged.
        Fernet(candidate)
        return candidate
    except (ValueError, TypeError):
        digest = hashlib.sha256(raw.encode()).digest()
        return base64.urlsafe_b64encode(digest)


def _resolve_key(cfg: Settings) -> bytes:
    """Resolve the Fernet key from settings, honouring the fail-closed posture.

    - configured value present → derive a valid Fernet key from it.
    - unset + debug → stable derived dev key + a one-time-style warning.
    - unset + non-debug → :class:`SeaChestKeyError` (fail closed).
    """
    configured = cfg.seachest_key
    if configured:
        return _derive_fernet_key(configured)

    if cfg.debug:
        logger.warning(
            "GRANDLINE_SEACHEST_KEY is unset; deriving a STABLE dev key for the "
            "Sea Chest. This is for local development only — set a real key in "
            "production (GRANDLINE_DEBUG must be false there)."
        )
        return _derive_fernet_key(_DEV_KEY_SEED)

    raise SeaChestKeyError(
        "GRANDLINE_SEACHEST_KEY is not set. The Sea Chest needs an encryption key "
        "to store credentials at rest. Set GRANDLINE_SEACHEST_KEY to a strong "
        "secret, or set GRANDLINE_DEBUG=true for local development."
    )


def _fernet(cfg: Settings | None = None) -> Fernet:
    """Build a :class:`Fernet` from the resolved key (per-call, no global cache)."""
    return Fernet(_resolve_key(cfg if cfg is not None else settings))


def encrypt(plaintext: str, *, cfg: Settings | None = None) -> bytes:
    """Encrypt a secret string, returning the Fernet token as bytes (ciphertext).

    Raises :class:`SeaChestKeyError` if no key is configured outside debug mode.
    Never logs the plaintext or the resulting ciphertext.
    """
    return _fernet(cfg).encrypt(plaintext.encode())


def decrypt(token: bytes, *, cfg: Settings | None = None) -> str:
    """Decrypt a Fernet token back to the original secret string.

    INTERNAL use only — this returns plaintext and must never feed an API response.
    Raises :class:`SeaChestKeyError` if no key is configured outside debug mode, and
    ``cryptography.fernet.InvalidToken`` if the token cannot be decrypted (e.g. the
    key changed). Never logs the plaintext or the token.
    """
    return _fernet(cfg).decrypt(token).decode()


__all__ = [
    "InvalidToken",
    "SeaChestKeyError",
    "decrypt",
    "encrypt",
]
