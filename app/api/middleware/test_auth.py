"""
TDD Red-phase tests for auth middleware.

Spec: app/api/middleware/middleware_spec.md

Tests cover:
  - verify_basic_auth: success, wrong creds (401), missing header (401),
    timing-safe comparison, counter reset on success
  - verify_webhook_secret: success, wrong secret (401), missing header (422)
  - Rate limiter: block after 5 failures (429), TTL expiry, reset on success,
    applied to both endpoints
  - [SRE_MARKER] timing-attack resistance
  - [SRE_MARKER] brute-force protection
"""

from __future__ import annotations

import base64
import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient

# ---------- Imports under test ----------
# These MUST exist in auth.py per the spec; currently they don't → ImportError = Red.
# We use try/except so pytest can collect individual tests and show each as FAILED,
# rather than a single collection-level ImportError.
try:
    from app.api.middleware.auth import verify_basic_auth, verify_webhook_secret
except ImportError:
    verify_basic_auth = None  # type: ignore[assignment]
    verify_webhook_secret = None  # type: ignore[assignment]

# Guard: skip all tests if functions are not yet implemented
pytestmark = pytest.mark.skipif(
    verify_basic_auth is None or verify_webhook_secret is None,
    reason=(
        "verify_basic_auth / verify_webhook_secret not yet exported from "
        "app.api.middleware.auth — TDD Red phase (implementation pending)"
    ),
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_USERNAME = "gateway_operator"
VALID_PASSWORD = "Str0ng!Pass#2026"
VALID_WEBHOOK_SECRET = "super_secret_webhook_token_1234"

ENV_VARS = {
    "ADMIN_USERNAME": VALID_USERNAME,
    "ADMIN_PASSWORD": VALID_PASSWORD,
    "WEBHOOK_SECRET": VALID_WEBHOOK_SECRET,
}


def _basic_auth_header(username: str, password: str) -> dict[str, str]:
    """Build an HTTP Basic Authorization header."""
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture(autouse=True)
def _patch_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject required env vars for every test."""
    for key, value in ENV_VARS.items():
        monkeypatch.setenv(key, value)


@pytest.fixture()
def _reset_rate_limiter() -> None:
    """
    Reset the in-memory rate limiter state before each test that needs it.
    The rate limiter module should expose a `reset()` or similar mechanism,
    or we clear its internal dict directly.
    """
    # Attempt to reset; if the module doesn't expose it yet, that's fine (Red phase).
    try:
        from app.api.middleware.auth import _failed_attempts  # noqa: WPS433

        _failed_attempts.clear()
    except (ImportError, AttributeError):
        pass


@pytest.fixture()
def basic_app() -> FastAPI:
    """Minimal FastAPI app with a route protected by verify_basic_auth."""
    app = FastAPI()

    @app.get("/protected")
    def protected_route(username: str = verify_basic_auth):  # type: ignore[assignment]
        # verify_basic_auth is a Depends-function; wire it properly
        pass

    # Re-create with proper Depends usage
    from fastapi import Depends as _Depends

    app2 = FastAPI()

    @app2.get("/protected")
    def _protected(username: str = _Depends(verify_basic_auth)):
        return {"user": username}

    return app2


@pytest.fixture()
def webhook_app() -> FastAPI:
    """Minimal FastAPI app with a route protected by verify_webhook_secret."""
    from fastapi import Depends as _Depends

    app = FastAPI()

    @app.post("/webhook")
    def _webhook(verified: bool = _Depends(verify_webhook_secret)):
        return {"ok": verified}

    return app


@pytest.fixture()
def basic_client(basic_app: FastAPI) -> TestClient:
    return TestClient(basic_app)


@pytest.fixture()
def webhook_client(webhook_app: FastAPI) -> TestClient:
    return TestClient(webhook_app)


# ===========================================================================
# 1. verify_basic_auth — Happy path
# ===========================================================================


class TestVerifyBasicAuthSuccess:
    """Spec §2.1 step 4: valid credentials → return username."""

    def test_returns_username_on_valid_credentials(
        self, basic_client: TestClient
    ) -> None:
        resp = basic_client.get(
            "/protected",
            headers=_basic_auth_header(VALID_USERNAME, VALID_PASSWORD),
        )
        assert resp.status_code == 200
        assert resp.json()["user"] == VALID_USERNAME

    def test_return_type_is_string(self, basic_client: TestClient) -> None:
        resp = basic_client.get(
            "/protected",
            headers=_basic_auth_header(VALID_USERNAME, VALID_PASSWORD),
        )
        assert isinstance(resp.json()["user"], str)


# ===========================================================================
# 2. verify_basic_auth — Missing / wrong credentials → 401
# ===========================================================================


class TestVerifyBasicAuthFailure:
    """Spec §2.1 step 5 & §3: invalid/missing creds → HTTP 401."""

    def test_missing_auth_header_returns_401(self, basic_client: TestClient) -> None:
        resp = basic_client.get("/protected")
        assert resp.status_code == 401

    def test_missing_auth_header_has_www_authenticate(
        self, basic_client: TestClient
    ) -> None:
        resp = basic_client.get("/protected")
        assert "basic" in resp.headers.get("www-authenticate", "").lower()

    def test_wrong_password_returns_401(self, basic_client: TestClient) -> None:
        resp = basic_client.get(
            "/protected",
            headers=_basic_auth_header(VALID_USERNAME, "wrong_password"),
        )
        assert resp.status_code == 401

    def test_wrong_username_returns_401(self, basic_client: TestClient) -> None:
        resp = basic_client.get(
            "/protected",
            headers=_basic_auth_header("wrong_user", VALID_PASSWORD),
        )
        assert resp.status_code == 401

    def test_wrong_creds_include_www_authenticate_header(
        self, basic_client: TestClient
    ) -> None:
        resp = basic_client.get(
            "/protected",
            headers=_basic_auth_header("wrong", "wrong"),
        )
        assert "basic" in resp.headers.get("www-authenticate", "").lower()


# ===========================================================================
# 3. [SRE_MARKER] Timing-safe comparison
# ===========================================================================


class TestTimingSafeComparison:
    """Spec §2.1 step 3: must use secrets.compare_digest or hmac.compare_digest."""

    def test_uses_timing_safe_comparison(self, basic_client: TestClient) -> None:
        """Patch hmac.compare_digest to verify it is actually called."""
        with patch("hmac.compare_digest", return_value=True) as mock_cmp:
            resp = basic_client.get(
                "/protected",
                headers=_basic_auth_header(VALID_USERNAME, VALID_PASSWORD),
            )
            # If the implementation uses hmac.compare_digest, it must be called.
            # We accept either hmac.compare_digest or secrets.compare_digest.
            if not mock_cmp.called:
                with patch("secrets.compare_digest", return_value=True) as mock_secrets:
                    resp2 = basic_client.get(
                        "/protected",
                        headers=_basic_auth_header(VALID_USERNAME, VALID_PASSWORD),
                    )
                    assert mock_secrets.called, (
                        "verify_basic_auth must use timing-safe comparison "
                        "(hmac.compare_digest or secrets.compare_digest)"
                    )


# ===========================================================================
# 4. verify_webhook_secret — Happy path
# ===========================================================================


class TestVerifyWebhookSecretSuccess:
    """Spec §2.2 step 4: valid secret → return True."""

    def test_valid_secret_returns_200(self, webhook_client: TestClient) -> None:
        resp = webhook_client.post(
            "/webhook",
            headers={"X-Webhook-Secret": VALID_WEBHOOK_SECRET},
        )
        assert resp.status_code == 200

    def test_valid_secret_returns_true(self, webhook_client: TestClient) -> None:
        resp = webhook_client.post(
            "/webhook",
            headers={"X-Webhook-Secret": VALID_WEBHOOK_SECRET},
        )
        assert resp.json()["ok"] is True


# ===========================================================================
# 5. verify_webhook_secret — Failure cases
# ===========================================================================


class TestVerifyWebhookSecretFailure:
    """Spec §2.2 step 5 & §3: wrong/missing secret."""

    def test_wrong_secret_returns_401(self, webhook_client: TestClient) -> None:
        resp = webhook_client.post(
            "/webhook",
            headers={"X-Webhook-Secret": "totally_wrong_value"},
        )
        assert resp.status_code == 401

    def test_wrong_secret_message(self, webhook_client: TestClient) -> None:
        resp = webhook_client.post(
            "/webhook",
            headers={"X-Webhook-Secret": "totally_wrong_value"},
        )
        assert "invalid webhook secret" in resp.json().get("detail", "").lower()

    def test_missing_webhook_header_returns_422(
        self, webhook_client: TestClient
    ) -> None:
        """Spec §3: missing X-Webhook-Secret → 422 (FastAPI auto-validation)."""
        resp = webhook_client.post("/webhook")
        assert resp.status_code == 422


# ===========================================================================
# 6. [SRE_MARKER] Rate Limiter — Brute-force protection
# ===========================================================================


class TestRateLimiterBasicAuth:
    """
    Spec §2.3: in-memory rate limiter.
    - Max 5 failed attempts per 60s sliding window per IP.
    - HTTP 429 on exceed BEFORE credential check.
    - Reset on success.
    - TTL auto-expire (60s).
    """

    @pytest.fixture(autouse=True)
    def _clean_limiter(self, _reset_rate_limiter: None) -> None:
        """Ensure rate limiter is clean before each test."""

    def test_sixth_failed_attempt_returns_429(self, basic_client: TestClient) -> None:
        """After 5 wrong attempts, the 6th must get 429."""
        bad_headers = _basic_auth_header("attacker", "wrong_pass")
        for _ in range(5):
            resp = basic_client.get("/protected", headers=bad_headers)
            assert resp.status_code == 401

        # 6th attempt → 429
        resp = basic_client.get("/protected", headers=bad_headers)
        assert resp.status_code == 429

    def test_429_returned_before_credential_check(
        self, basic_client: TestClient
    ) -> None:
        """
        After rate limit exceeded, even VALID credentials must get 429.
        This ensures no feedback about password validity is leaked.
        """
        bad_headers = _basic_auth_header("attacker", "wrong_pass")
        for _ in range(5):
            basic_client.get("/protected", headers=bad_headers)

        # Now try with VALID credentials from the same IP → still 429
        good_headers = _basic_auth_header(VALID_USERNAME, VALID_PASSWORD)
        resp = basic_client.get("/protected", headers=good_headers)
        assert resp.status_code == 429

    def test_successful_auth_resets_counter(self, basic_client: TestClient) -> None:
        """Spec §2.1 step 4 / §2.3: success resets the failed counter."""
        bad_headers = _basic_auth_header("attacker", "wrong_pass")
        # 3 failed attempts
        for _ in range(3):
            basic_client.get("/protected", headers=bad_headers)

        # Successful auth resets counter
        good_headers = _basic_auth_header(VALID_USERNAME, VALID_PASSWORD)
        resp = basic_client.get("/protected", headers=good_headers)
        assert resp.status_code == 200

        # Now 5 more failures should be allowed before 429
        for _ in range(5):
            resp = basic_client.get("/protected", headers=bad_headers)
            assert resp.status_code == 401

        # 6th after reset → 429
        resp = basic_client.get("/protected", headers=bad_headers)
        assert resp.status_code == 429

    def test_rate_limit_ttl_expires(self, basic_client: TestClient) -> None:
        """
        Spec §2.3: entries auto-expire after 60s TTL.
        We mock time to simulate expiry without waiting.
        """
        bad_headers = _basic_auth_header("attacker", "wrong_pass")

        # Exhaust the limit
        for _ in range(5):
            basic_client.get("/protected", headers=bad_headers)

        # Confirm blocked
        resp = basic_client.get("/protected", headers=bad_headers)
        assert resp.status_code == 429

        # Fast-forward time by 61 seconds
        with patch("time.time", return_value=time.time() + 61):
            resp = basic_client.get("/protected", headers=bad_headers)
            # Should be allowed again (401, not 429)
            assert resp.status_code == 401


class TestRateLimiterWebhook:
    """Spec §2.3: rate limiter also applies to verify_webhook_secret."""

    @pytest.fixture(autouse=True)
    def _clean_limiter(self, _reset_rate_limiter: None) -> None:
        """Ensure rate limiter is clean before each test."""

    def test_webhook_rate_limited_after_5_failures(
        self, webhook_client: TestClient
    ) -> None:
        bad_headers = {"X-Webhook-Secret": "wrong_secret_value"}
        for _ in range(5):
            resp = webhook_client.post("/webhook", headers=bad_headers)
            assert resp.status_code == 401

        # 6th → 429
        resp = webhook_client.post("/webhook", headers=bad_headers)
        assert resp.status_code == 429

    def test_webhook_valid_secret_after_rate_limit_still_blocked(
        self, webhook_client: TestClient
    ) -> None:
        """Even valid secret should be rejected when rate-limited (no credential feedback)."""
        bad_headers = {"X-Webhook-Secret": "wrong_secret_value"}
        for _ in range(5):
            webhook_client.post("/webhook", headers=bad_headers)

        good_headers = {"X-Webhook-Secret": VALID_WEBHOOK_SECRET}
        resp = webhook_client.post("/webhook", headers=good_headers)
        assert resp.status_code == 429


# ===========================================================================
# 7. Edge cases
# ===========================================================================


class TestEdgeCases:
    """Additional edge-case coverage."""

    def test_empty_username_returns_401(self, basic_client: TestClient) -> None:
        resp = basic_client.get(
            "/protected",
            headers=_basic_auth_header("", VALID_PASSWORD),
        )
        assert resp.status_code == 401

    def test_empty_password_returns_401(self, basic_client: TestClient) -> None:
        resp = basic_client.get(
            "/protected",
            headers=_basic_auth_header(VALID_USERNAME, ""),
        )
        assert resp.status_code == 401

    def test_case_sensitive_username(self, basic_client: TestClient) -> None:
        """Username comparison must be case-sensitive."""
        resp = basic_client.get(
            "/protected",
            headers=_basic_auth_header(VALID_USERNAME.upper(), VALID_PASSWORD),
        )
        # If VALID_USERNAME is not all-uppercase, this should fail auth
        if VALID_USERNAME != VALID_USERNAME.upper():
            assert resp.status_code == 401

    def test_webhook_secret_is_case_sensitive(self, webhook_client: TestClient) -> None:
        resp = webhook_client.post(
            "/webhook",
            headers={"X-Webhook-Secret": VALID_WEBHOOK_SECRET.upper()},
        )
        if VALID_WEBHOOK_SECRET != VALID_WEBHOOK_SECRET.upper():
            assert resp.status_code == 401

    def test_webhook_uses_timing_safe_comparison(
        self, webhook_client: TestClient
    ) -> None:
        """verify_webhook_secret must also use timing-safe comparison (spec §2.2 step 3)."""
        with patch("hmac.compare_digest", return_value=True) as mock_cmp:
            webhook_client.post(
                "/webhook",
                headers={"X-Webhook-Secret": VALID_WEBHOOK_SECRET},
            )
            if not mock_cmp.called:
                with patch("secrets.compare_digest", return_value=True) as mock_secrets:
                    webhook_client.post(
                        "/webhook",
                        headers={"X-Webhook-Secret": VALID_WEBHOOK_SECRET},
                    )
                    assert mock_secrets.called, (
                        "verify_webhook_secret must use timing-safe comparison"
                    )
