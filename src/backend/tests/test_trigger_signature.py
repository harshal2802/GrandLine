"""Tests for GitHub webhook HMAC signature verification (no DB)."""

from __future__ import annotations

import hashlib
import hmac
from unittest.mock import patch

from app.services.trigger_service import TriggerService, verify_github_signature

SECRET = "s3cr3t-bottle"
BODY = b'{"action":"opened","issue":{"number":7}}'


def _sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class TestVerifyGithubSignature:
    def test_valid_signature_passes(self) -> None:
        assert verify_github_signature(BODY, _sign(BODY, SECRET), SECRET) is True

    def test_tampered_body_fails(self) -> None:
        header = _sign(BODY, SECRET)
        tampered = BODY + b" "
        assert verify_github_signature(tampered, header, SECRET) is False

    def test_wrong_secret_fails(self) -> None:
        header = _sign(BODY, "other-secret")
        assert verify_github_signature(BODY, header, SECRET) is False

    def test_missing_header_fails(self) -> None:
        assert verify_github_signature(BODY, None, SECRET) is False

    def test_malformed_header_fails(self) -> None:
        # No "sha256=" prefix.
        bare = hmac.new(SECRET.encode("utf-8"), BODY, hashlib.sha256).hexdigest()
        assert verify_github_signature(BODY, bare, SECRET) is False

    def test_none_secret_fails(self) -> None:
        assert verify_github_signature(BODY, _sign(BODY, SECRET), None) is False

    def test_uses_constant_time_compare(self) -> None:
        with patch(
            "app.services.trigger_service.hmac.compare_digest",
            wraps=hmac.compare_digest,
        ) as cmp:
            verify_github_signature(BODY, _sign(BODY, SECRET), SECRET)
        cmp.assert_called_once()

    def test_static_method_handle_matches(self) -> None:
        header = _sign(BODY, SECRET)
        assert TriggerService.verify_github_signature(BODY, header, SECRET) is True
        assert TriggerService.verify_github_signature(BODY, header, None) is False
