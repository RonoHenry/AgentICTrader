"""
Test suite for the Auth Service (Task 34).

TDD Phase: RED → GREEN → REFACTOR

Tests cover:
- POST /auth/register creates user and returns JWT
- POST /auth/login returns access token (15min TTL) and refresh token (7-day TTL)
- POST /auth/refresh returns new access token
- Admin role has full access, Trader has own data + agent control, Viewer is read-only
- Broker API keys are encrypted before storing in MongoDB
- Invalid credentials return 401

Validates: Requirements FR-10
"""
from __future__ import annotations

import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Path setup — ensure workspace root is importable
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

import httpx
from httpx import AsyncClient, ASGITransport
import mongomock_motor

from services.auth.main import (
    AuthService,
    UserRole,
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    BrokerKeyRequest,
    create_app,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FERNET_TEST_KEY = "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q="  # 32-byte base64


@pytest.fixture
def mongo_client():
    """Return a mongomock_motor async client for testing."""
    return mongomock_motor.AsyncMongoMockClient()


@pytest.fixture
def mongo_db(mongo_client):
    """Return the test database."""
    return mongo_client["agentictrader_test"]


@pytest.fixture
def auth_service(mongo_db):
    """Return an AuthService instance backed by mongomock."""
    return AuthService(
        db=mongo_db,
        secret_key="test-secret-key-for-jwt-signing-must-be-long-enough",
        broker_key_encryption_key=FERNET_TEST_KEY,
    )


@pytest.fixture
def app(mongo_db):
    """Return a FastAPI app wired with mongomock."""
    return create_app(
        db=mongo_db,
        secret_key="test-secret-key-for-jwt-signing-must-be-long-enough",
        broker_key_encryption_key=FERNET_TEST_KEY,
    )


@pytest.fixture
async def client(app):
    """Return an async HTTP test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# TestTokenTTLConstants — verify token TTL constants
# ---------------------------------------------------------------------------

class TestTokenTTLConstants:
    """Verify token TTL constants match FR-10 requirements.

    Validates: Requirements FR-10
    """

    def test_access_token_ttl_is_15_minutes(self):
        """Test: access token TTL is 15 minutes.

        Validates: Requirements FR-10
        """
        assert ACCESS_TOKEN_EXPIRE_MINUTES == 15

    def test_refresh_token_ttl_is_7_days(self):
        """Test: refresh token TTL is 7 days.

        Validates: Requirements FR-10
        """
        assert REFRESH_TOKEN_EXPIRE_DAYS == 7


# ---------------------------------------------------------------------------
# TestRegister — POST /auth/register
# ---------------------------------------------------------------------------

class TestRegister:
    """Tests for POST /auth/register endpoint.

    Validates: Requirements FR-10
    """

    async def test_register_creates_user_and_returns_tokens(self, client):
        """Test: POST /auth/register creates a user and returns access + refresh tokens.

        Validates: Requirements FR-10
        """
        response = await client.post(
            "/auth/register",
            json={
                "username": "trader1",
                "email": "trader1@example.com",
                "password": "SecurePass123!",
                "role": "TRADER",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_register_returns_jwt_with_correct_claims(self, client):
        """Test: returned access token contains sub, role, type, exp claims.

        Validates: Requirements FR-10
        """
        from jose import jwt

        response = await client.post(
            "/auth/register",
            json={
                "username": "trader2",
                "email": "trader2@example.com",
                "password": "SecurePass123!",
                "role": "TRADER",
            },
        )
        assert response.status_code == 201
        data = response.json()

        # Decode without verification to inspect claims
        token = data["access_token"]
        claims = jwt.get_unverified_claims(token)
        assert "sub" in claims
        assert claims["role"] == "TRADER"
        assert claims["type"] == "access"
        assert "exp" in claims

    async def test_register_duplicate_username_returns_409(self, client):
        """Test: registering with a duplicate username returns 409.

        Validates: Requirements FR-10
        """
        payload = {
            "username": "dupuser",
            "email": "dup@example.com",
            "password": "SecurePass123!",
            "role": "VIEWER",
        }
        r1 = await client.post("/auth/register", json=payload)
        assert r1.status_code == 201

        r2 = await client.post("/auth/register", json=payload)
        assert r2.status_code == 409

    async def test_register_stores_hashed_password(self, client, mongo_db):
        """Test: password is stored as a bcrypt hash, not plaintext.

        Validates: Requirements FR-10
        """
        await client.post(
            "/auth/register",
            json={
                "username": "hashtest",
                "email": "hashtest@example.com",
                "password": "PlainTextPass!",
                "role": "VIEWER",
            },
        )
        user = await mongo_db["users"].find_one({"username": "hashtest"})
        assert user is not None
        assert user["hashed_password"] != "PlainTextPass!"
        assert user["hashed_password"].startswith("$2b$")  # bcrypt prefix


# ---------------------------------------------------------------------------
# TestLogin — POST /auth/login
# ---------------------------------------------------------------------------

class TestLogin:
    """Tests for POST /auth/login endpoint.

    Validates: Requirements FR-10
    """

    async def test_login_returns_access_and_refresh_tokens(self, client):
        """Test: POST /auth/login returns access token and refresh token.

        Validates: Requirements FR-10
        """
        # Register first
        await client.post(
            "/auth/register",
            json={
                "username": "loginuser",
                "email": "login@example.com",
                "password": "LoginPass123!",
                "role": "TRADER",
            },
        )

        response = await client.post(
            "/auth/login",
            json={"username": "loginuser", "password": "LoginPass123!"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_access_token_has_15min_ttl(self, client):
        """Test: access token expires in 15 minutes.

        Validates: Requirements FR-10
        """
        from jose import jwt
        import time

        await client.post(
            "/auth/register",
            json={
                "username": "ttluser",
                "email": "ttl@example.com",
                "password": "TTLPass123!",
                "role": "TRADER",
            },
        )
        response = await client.post(
            "/auth/login",
            json={"username": "ttluser", "password": "TTLPass123!"},
        )
        data = response.json()
        claims = jwt.get_unverified_claims(data["access_token"])
        now = int(time.time())
        ttl_seconds = claims["exp"] - now
        # Should be approximately 15 minutes (900 seconds), allow ±30s tolerance
        assert 870 <= ttl_seconds <= 930, f"Access token TTL {ttl_seconds}s not ~900s"

    async def test_login_refresh_token_has_7day_ttl(self, client):
        """Test: refresh token expires in 7 days.

        Validates: Requirements FR-10
        """
        from jose import jwt
        import time

        await client.post(
            "/auth/register",
            json={
                "username": "refreshttl",
                "email": "refreshttl@example.com",
                "password": "RefreshPass123!",
                "role": "TRADER",
            },
        )
        response = await client.post(
            "/auth/login",
            json={"username": "refreshttl", "password": "RefreshPass123!"},
        )
        data = response.json()
        claims = jwt.get_unverified_claims(data["refresh_token"])
        now = int(time.time())
        ttl_seconds = claims["exp"] - now
        seven_days = 7 * 24 * 3600
        # Allow ±60s tolerance
        assert seven_days - 60 <= ttl_seconds <= seven_days + 60, (
            f"Refresh token TTL {ttl_seconds}s not ~{seven_days}s"
        )

    async def test_login_refresh_token_type_claim(self, client):
        """Test: refresh token has type='refresh' in JWT claims.

        Validates: Requirements FR-10
        """
        from jose import jwt

        await client.post(
            "/auth/register",
            json={
                "username": "refreshtype",
                "email": "refreshtype@example.com",
                "password": "RefreshType123!",
                "role": "TRADER",
            },
        )
        response = await client.post(
            "/auth/login",
            json={"username": "refreshtype", "password": "RefreshType123!"},
        )
        data = response.json()
        claims = jwt.get_unverified_claims(data["refresh_token"])
        assert claims["type"] == "refresh"

    async def test_login_invalid_password_returns_401(self, client):
        """Test: invalid password returns 401 Unauthorized.

        Validates: Requirements FR-10
        """
        await client.post(
            "/auth/register",
            json={
                "username": "wrongpass",
                "email": "wrongpass@example.com",
                "password": "CorrectPass123!",
                "role": "VIEWER",
            },
        )
        response = await client.post(
            "/auth/login",
            json={"username": "wrongpass", "password": "WrongPass999!"},
        )
        assert response.status_code == 401

    async def test_login_nonexistent_user_returns_401(self, client):
        """Test: login with non-existent username returns 401.

        Validates: Requirements FR-10
        """
        response = await client.post(
            "/auth/login",
            json={"username": "ghost_user", "password": "AnyPass123!"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# TestRefresh — POST /auth/refresh
# ---------------------------------------------------------------------------

class TestRefresh:
    """Tests for POST /auth/refresh endpoint.

    Validates: Requirements FR-10
    """

    async def test_refresh_returns_new_access_token(self, client):
        """Test: POST /auth/refresh returns a new access token.

        Validates: Requirements FR-10
        """
        await client.post(
            "/auth/register",
            json={
                "username": "refreshuser",
                "email": "refresh@example.com",
                "password": "RefreshMe123!",
                "role": "TRADER",
            },
        )
        login_resp = await client.post(
            "/auth/login",
            json={"username": "refreshuser", "password": "RefreshMe123!"},
        )
        refresh_token = login_resp.json()["refresh_token"]

        response = await client.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_refresh_with_access_token_returns_401(self, client):
        """Test: using an access token as refresh token returns 401.

        Validates: Requirements FR-10
        """
        await client.post(
            "/auth/register",
            json={
                "username": "wrongtoken",
                "email": "wrongtoken@example.com",
                "password": "WrongToken123!",
                "role": "TRADER",
            },
        )
        login_resp = await client.post(
            "/auth/login",
            json={"username": "wrongtoken", "password": "WrongToken123!"},
        )
        access_token = login_resp.json()["access_token"]

        # Use access token where refresh token is expected
        response = await client.post(
            "/auth/refresh",
            json={"refresh_token": access_token},
        )
        assert response.status_code == 401

    async def test_refresh_with_invalid_token_returns_401(self, client):
        """Test: invalid/tampered refresh token returns 401.

        Validates: Requirements FR-10
        """
        response = await client.post(
            "/auth/refresh",
            json={"refresh_token": "this.is.not.a.valid.token"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# TestRBAC — Role-Based Access Control
# ---------------------------------------------------------------------------

class TestRBAC:
    """Tests for RBAC: Admin, Trader, Viewer roles.

    Validates: Requirements FR-10
    """

    async def _register_and_login(self, client, username: str, role: str) -> str:
        """Helper: register a user and return their access token."""
        await client.post(
            "/auth/register",
            json={
                "username": username,
                "email": f"{username}@example.com",
                "password": "RBACPass123!",
                "role": role,
            },
        )
        resp = await client.post(
            "/auth/login",
            json={"username": username, "password": "RBACPass123!"},
        )
        return resp.json()["access_token"]

    async def test_get_me_returns_own_profile(self, client):
        """Test: GET /auth/me returns the authenticated user's profile.

        Validates: Requirements FR-10
        """
        token = await self._register_and_login(client, "meuser", "TRADER")
        response = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "meuser"
        assert data["role"] == "TRADER"

    async def test_get_me_without_token_returns_401(self, client):
        """Test: GET /auth/me without token returns 401.

        Validates: Requirements FR-10
        """
        response = await client.get("/auth/me")
        assert response.status_code == 401

    async def test_admin_role_encoded_in_token(self, client):
        """Test: Admin role is correctly encoded in JWT.

        Validates: Requirements FR-10
        """
        from jose import jwt

        token = await self._register_and_login(client, "adminuser", "ADMIN")
        claims = jwt.get_unverified_claims(token)
        assert claims["role"] == "ADMIN"

    async def test_trader_role_encoded_in_token(self, client):
        """Test: Trader role is correctly encoded in JWT.

        Validates: Requirements FR-10
        """
        from jose import jwt

        token = await self._register_and_login(client, "traderuser", "TRADER")
        claims = jwt.get_unverified_claims(token)
        assert claims["role"] == "TRADER"

    async def test_viewer_role_encoded_in_token(self, client):
        """Test: Viewer role is correctly encoded in JWT.

        Validates: Requirements FR-10
        """
        from jose import jwt

        token = await self._register_and_login(client, "vieweruser", "VIEWER")
        claims = jwt.get_unverified_claims(token)
        assert claims["role"] == "VIEWER"

    async def test_viewer_cannot_store_broker_keys(self, client):
        """Test: Viewer role cannot store broker API keys (403 Forbidden).

        Validates: Requirements FR-10
        """
        token = await self._register_and_login(client, "viewerbroker", "VIEWER")
        # Get user_id from /auth/me
        me_resp = await client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        user_id = me_resp.json()["user_id"]

        response = await client.post(
            f"/users/{user_id}/broker-keys",
            json={"broker_name": "OANDA", "api_key": "secret-api-key-123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    async def test_trader_can_store_own_broker_keys(self, client):
        """Test: Trader role can store their own broker API keys.

        Validates: Requirements FR-10
        """
        token = await self._register_and_login(client, "traderbroker", "TRADER")
        me_resp = await client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        user_id = me_resp.json()["user_id"]

        response = await client.post(
            f"/users/{user_id}/broker-keys",
            json={"broker_name": "OANDA", "api_key": "secret-api-key-123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201

    async def test_admin_can_store_broker_keys_for_any_user(self, client):
        """Test: Admin role can store broker keys for any user.

        Validates: Requirements FR-10
        """
        # Register a target trader
        await client.post(
            "/auth/register",
            json={
                "username": "targettrader",
                "email": "target@example.com",
                "password": "TargetPass123!",
                "role": "TRADER",
            },
        )
        target_resp = await client.post(
            "/auth/login",
            json={"username": "targettrader", "password": "TargetPass123!"},
        )
        target_token = target_resp.json()["access_token"]
        target_me = await client.get(
            "/auth/me", headers={"Authorization": f"Bearer {target_token}"}
        )
        target_user_id = target_me.json()["user_id"]

        # Admin stores keys for the target trader
        admin_token = await self._register_and_login(client, "adminbroker", "ADMIN")
        response = await client.post(
            f"/users/{target_user_id}/broker-keys",
            json={"broker_name": "OANDA", "api_key": "admin-set-key-456"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 201


# ---------------------------------------------------------------------------
# TestBrokerKeyEncryption — encrypted broker key storage
# ---------------------------------------------------------------------------

class TestBrokerKeyEncryption:
    """Tests for broker API key encryption at rest.

    Validates: Requirements FR-10
    """

    async def _register_and_login(self, client, username: str, role: str = "TRADER") -> tuple[str, str]:
        """Helper: register a user and return (access_token, user_id)."""
        await client.post(
            "/auth/register",
            json={
                "username": username,
                "email": f"{username}@example.com",
                "password": "EncryptPass123!",
                "role": role,
            },
        )
        resp = await client.post(
            "/auth/login",
            json={"username": username, "password": "EncryptPass123!"},
        )
        token = resp.json()["access_token"]
        me_resp = await client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        user_id = me_resp.json()["user_id"]
        return token, user_id

    async def test_broker_key_stored_encrypted_not_plaintext(self, client, mongo_db):
        """Test: broker API key is stored encrypted, not as plaintext.

        Validates: Requirements FR-10
        """
        token, user_id = await self._register_and_login(client, "encryptuser")
        plaintext_key = "my-plaintext-broker-api-key-12345"

        await client.post(
            f"/users/{user_id}/broker-keys",
            json={"broker_name": "OANDA", "api_key": plaintext_key},
            headers={"Authorization": f"Bearer {token}"},
        )

        # Check MongoDB — the stored value must NOT be the plaintext key
        record = await mongo_db["broker_keys"].find_one({"user_id": user_id})
        assert record is not None
        assert record["encrypted_api_key"] != plaintext_key

    async def test_broker_key_can_be_decrypted_with_fernet(self, client, mongo_db):
        """Test: stored broker key can be decrypted with the Fernet key.

        Validates: Requirements FR-10
        """
        from cryptography.fernet import Fernet
        import base64

        token, user_id = await self._register_and_login(client, "decryptuser")
        plaintext_key = "decrypt-me-broker-key-67890"

        await client.post(
            f"/users/{user_id}/broker-keys",
            json={"broker_name": "OANDA", "api_key": plaintext_key},
            headers={"Authorization": f"Bearer {token}"},
        )

        record = await mongo_db["broker_keys"].find_one({"user_id": user_id})
        encrypted = record["encrypted_api_key"]

        # Decrypt using the test Fernet key
        # The test key is a base64-encoded 32-byte string; Fernet needs a URL-safe base64 key
        fernet_key = base64.urlsafe_b64encode(
            base64.b64decode(FERNET_TEST_KEY + "==")[:32]
        )
        f = Fernet(fernet_key)
        decrypted = f.decrypt(encrypted.encode()).decode()
        assert decrypted == plaintext_key

    async def test_broker_key_stored_with_user_id(self, client, mongo_db):
        """Test: broker key record is keyed by user_id.

        Validates: Requirements FR-10
        """
        token, user_id = await self._register_and_login(client, "keyeduser")

        await client.post(
            f"/users/{user_id}/broker-keys",
            json={"broker_name": "DERIV", "api_key": "keyed-api-key-abc"},
            headers={"Authorization": f"Bearer {token}"},
        )

        record = await mongo_db["broker_keys"].find_one({"user_id": user_id})
        assert record is not None
        assert record["user_id"] == user_id
        assert record["broker_name"] == "DERIV"


# ---------------------------------------------------------------------------
# TestInvalidCredentials — 401 responses
# ---------------------------------------------------------------------------

class TestInvalidCredentials:
    """Tests for 401 responses on invalid credentials.

    Validates: Requirements FR-10
    """

    async def test_protected_endpoint_with_invalid_token_returns_401(self, client):
        """Test: accessing protected endpoint with invalid token returns 401.

        Validates: Requirements FR-10
        """
        response = await client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert response.status_code == 401

    async def test_protected_endpoint_with_expired_token_returns_401(self, client):
        """Test: accessing protected endpoint with expired token returns 401.

        Validates: Requirements FR-10
        """
        from jose import jwt
        import time

        # Create an already-expired token
        expired_token = jwt.encode(
            {
                "sub": "some-user-id",
                "role": "TRADER",
                "type": "access",
                "exp": int(time.time()) - 3600,  # expired 1 hour ago
            },
            "test-secret-key-for-jwt-signing-must-be-long-enough",
            algorithm="HS256",
        )
        response = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401

    async def test_login_wrong_password_does_not_leak_user_existence(self, client):
        """Test: wrong password and non-existent user both return 401 (no info leak).

        Validates: Requirements FR-10
        """
        # Register a real user
        await client.post(
            "/auth/register",
            json={
                "username": "realuser",
                "email": "real@example.com",
                "password": "RealPass123!",
                "role": "VIEWER",
            },
        )

        # Wrong password for real user
        r1 = await client.post(
            "/auth/login",
            json={"username": "realuser", "password": "WrongPass!"},
        )
        # Non-existent user
        r2 = await client.post(
            "/auth/login",
            json={"username": "fakeuser", "password": "AnyPass!"},
        )

        assert r1.status_code == 401
        assert r2.status_code == 401
        # Both should return the same generic error message
        assert r1.json()["detail"] == r2.json()["detail"]
