"""Tests for the Sea Chest crypto helper (pure — no DB)."""

from __future__ import annotations

import base64
import hashlib

import pytest
from cryptography.fernet import Fernet

from app.core.config import Settings
from app.core.seachest_crypto import SeaChestKeyError, decrypt, encrypt

SECRET = "sk-ant-super-secret-token-value"


def _cfg(*, key: str | None, debug: bool) -> Settings:
    return Settings(seachest_key=key, debug=debug)


class TestRoundTrip:
    def test_encrypt_decrypt_round_trip(self) -> None:
        cfg = _cfg(key="some-arbitrary-passphrase", debug=False)
        token = encrypt(SECRET, cfg=cfg)
        assert decrypt(token, cfg=cfg) == SECRET

    def test_ciphertext_differs_from_plaintext_bytes(self) -> None:
        cfg = _cfg(key="some-arbitrary-passphrase", debug=False)
        token = encrypt(SECRET, cfg=cfg)
        assert isinstance(token, bytes)
        assert token != SECRET.encode()
        # The plaintext must not appear anywhere in the ciphertext bytes.
        assert SECRET.encode() not in token


class TestKeyDerivation:
    def test_arbitrary_string_is_derived_deterministically(self) -> None:
        cfg = _cfg(key="not-a-fernet-key", debug=False)
        # Same arbitrary value → decryptable across separate fernet instances.
        token = encrypt(SECRET, cfg=cfg)
        assert decrypt(token, cfg=_cfg(key="not-a-fernet-key", debug=False)) == SECRET

    def test_already_valid_fernet_key_accepted_as_is(self) -> None:
        valid_key = Fernet.generate_key().decode()
        cfg = _cfg(key=valid_key, debug=False)
        token = encrypt(SECRET, cfg=cfg)
        # The same raw key string round-trips.
        assert decrypt(token, cfg=_cfg(key=valid_key, debug=False)) == SECRET

    def test_derivation_matches_sha256_urlsafe_b64(self) -> None:
        raw = "not-a-fernet-key"
        expected = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
        token = encrypt(SECRET, cfg=_cfg(key=raw, debug=False))
        # Decrypt with the explicitly-derived Fernet to prove the derivation.
        assert Fernet(expected).decrypt(token).decode() == SECRET

    def test_different_keys_cannot_cross_decrypt(self) -> None:
        token = encrypt(SECRET, cfg=_cfg(key="key-a", debug=False))
        from cryptography.fernet import InvalidToken

        with pytest.raises(InvalidToken):
            decrypt(token, cfg=_cfg(key="key-b", debug=False))


class TestMissingKeyGuard:
    def test_debug_derives_stable_dev_key_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        cfg = _cfg(key=None, debug=True)
        with caplog.at_level("WARNING"):
            token = encrypt(SECRET, cfg=cfg)
        # Stable: a separate unset+debug config decrypts the same ciphertext.
        assert decrypt(token, cfg=_cfg(key=None, debug=True)) == SECRET
        assert any("SEACHEST_KEY" in r.message for r in caplog.records)

    def test_non_debug_unset_key_raises(self) -> None:
        cfg = _cfg(key=None, debug=False)
        with pytest.raises(SeaChestKeyError):
            encrypt(SECRET, cfg=cfg)

    def test_key_error_message_has_no_secret(self) -> None:
        cfg = _cfg(key=None, debug=False)
        with pytest.raises(SeaChestKeyError) as exc:
            encrypt(SECRET, cfg=cfg)
        assert SECRET not in str(exc.value)
