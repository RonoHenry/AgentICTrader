"""Auth Service FastAPI service.

Implements JWT-based authentication, RBAC, and encrypted broker key storage.

Endpoints:
  POST /auth/register  — create user, return access + refresh tokens
  POST /auth/login     — verify credentials, return access + refresh tokens
  POST /auth/refresh   — exchange refresh token for new access token
  GET  /auth/me        — return current user profile (requires auth)
  POST /users/{user_id}/broker-keys — store encrypted broker key (Trader/Admin only)

JWT payload fields:
  sub:  user_id
  role: user role (ADMIN/TRADER/VIEWER)
  exp:  expiry timestamp
  type: "access" or "refresh"

RBAC rules:
  Admin:  full access to all resources
  Trader: own data + agent control
  Viewer: read-only (cannot control agent or modify data)

Broker key encryption:
  Uses Fernet symmetric encryption (cryptography package).
  Encryption key read from BROKER_KEY_ENCRYPTION_KEY env var.

Validates: Requirements FR-10
"""
from __future__ import annotations

import base64
import logging
import os
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

import bcrypt as _bcrypt_lib
from bson import ObjectId
from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
REFRESH_TOKEN_EXPIRE_DAYS: int = 7
ALGORITHM: str = "HS256"

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    TRADER = "TRADER"
    VIEWER = "VIEWER"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    role: UserRole = UserRole.VIEWER


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"


class UserProfile(BaseModel):
    user_id: str
    username: str
    email: str
    role: str


class BrokerKeyRequest(BaseModel):
    broker_name: str
    api_key: str


class BrokerKeyResponse(BaseModel):
    user_id: str
    broker_name: str
    message: str = "Broker key stored successfully"


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
# Use bcrypt directly to avoid passlib/bcrypt 5.x incompatibility.


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = _bcrypt_lib.gensalt()
    return _bcrypt_lib.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return _bcrypt_lib.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ---------------------------------------------------------------------------
# Fernet encryption helpers
# ---------------------------------------------------------------------------


def _build_fernet(raw_key: str) -> Fernet:
    """Build a Fernet instance from a raw base64-encoded 32-byte key string."""
    # Decode the raw key bytes, take first 32 bytes, re-encode as URL-safe base64
    decoded = base64.b64decode(raw_key + "==")[:32]
    fernet_key = base64.urlsafe_b64encode(decoded)
    return Fernet(fernet_key)


def encrypt_broker_key(plaintext: str, raw_key: str) -> str:
    """Encrypt a broker API key using Fernet symmetric encryption."""
    f = _build_fernet(raw_key)
    return f.encrypt(plaintext.encode()).decode()


def decrypt_broker_key(ciphertext: str, raw_key: str) -> str:
    """Decrypt a broker API key."""
    f = _build_fernet(raw_key)
    return f.decrypt(ciphertext.encode()).decode()


# ---------------------------------------------------------------------------
# AuthService — core business logic
# ---------------------------------------------------------------------------


class AuthService:
    """Core authentication and authorisation logic.

    Args:
        db: An async Motor (or mongomock_motor) database instance.
        secret_key: Secret key for JWT signing.
        broker_key_encryption_key: Raw base64-encoded 32-byte key for Fernet encryption.
    """

    def __init__(self, db, secret_key: str, broker_key_encryption_key: str) -> None:
        self._db = db
        self._secret_key = secret_key
        self._broker_enc_key = broker_key_encryption_key

    # ------------------------------------------------------------------
    # Token creation
    # ------------------------------------------------------------------

    def _create_token(
        self,
        user_id: str,
        role: str,
        token_type: str,
        expire_delta: timedelta,
    ) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "role": role,
            "type": token_type,
            "exp": now + expire_delta,
            "iat": now,
        }
        return jwt.encode(payload, self._secret_key, algorithm=ALGORITHM)

    def create_access_token(self, user_id: str, role: str) -> str:
        return self._create_token(
            user_id,
            role,
            "access",
            timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        )

    def create_refresh_token(self, user_id: str, role: str) -> str:
        return self._create_token(
            user_id,
            role,
            "refresh",
            timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )

    # ------------------------------------------------------------------
    # Token verification
    # ------------------------------------------------------------------

    def verify_token(self, token: str, expected_type: str = "access") -> dict:
        """Decode and validate a JWT. Raises HTTPException on failure."""
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[ALGORITHM])
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if payload.get("type") != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Expected token type '{expected_type}', got '{payload.get('type')}'",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload

    # ------------------------------------------------------------------
    # Register
    # ------------------------------------------------------------------

    async def register(self, request: RegisterRequest) -> TokenResponse:
        """Create a new user and return tokens."""
        existing = await self._db["users"].find_one({"username": request.username})
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists",
            )

        hashed = hash_password(request.password)
        user_doc = {
            "username": request.username,
            "email": request.email,
            "hashed_password": hashed,
            "role": request.role.value,
        }
        result = await self._db["users"].insert_one(user_doc)
        user_id = str(result.inserted_id)

        access_token = self.create_access_token(user_id, request.role.value)
        refresh_token = self.create_refresh_token(user_id, request.role.value)
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def login(self, request: LoginRequest) -> TokenResponse:
        """Verify credentials and return tokens."""
        user = await self._db["users"].find_one({"username": request.username})
        if not user or not verify_password(request.password, user["hashed_password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = str(user["_id"])
        role = user["role"]
        access_token = self.create_access_token(user_id, role)
        refresh_token = self.create_refresh_token(user_id, role)
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    async def refresh(self, refresh_token: str) -> TokenResponse:
        """Exchange a refresh token for a new access token."""
        payload = self.verify_token(refresh_token, expected_type="refresh")
        user_id = payload["sub"]
        role = payload["role"]
        new_access = self.create_access_token(user_id, role)
        return TokenResponse(access_token=new_access)

    # ------------------------------------------------------------------
    # Get current user
    # ------------------------------------------------------------------

    async def get_current_user(self, token: str) -> UserProfile:
        """Decode access token and return user profile from DB."""
        payload = self.verify_token(token, expected_type="access")
        user_id = payload["sub"]

        try:
            oid = ObjectId(user_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token subject",
            )

        user = await self._db["users"].find_one({"_id": oid})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        return UserProfile(
            user_id=user_id,
            username=user["username"],
            email=user["email"],
            role=user["role"],
        )

    # ------------------------------------------------------------------
    # Broker key storage
    # ------------------------------------------------------------------

    async def store_broker_key(
        self,
        requesting_user_id: str,
        requesting_role: str,
        target_user_id: str,
        request: BrokerKeyRequest,
    ) -> BrokerKeyResponse:
        """Encrypt and store a broker API key.

        Trader can only store keys for themselves.
        Admin can store keys for any user.
        Viewer cannot store keys.
        """
        if requesting_role == UserRole.VIEWER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Viewer role cannot store broker keys",
            )
        if requesting_role == UserRole.TRADER and requesting_user_id != target_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Traders can only store their own broker keys",
            )

        encrypted = encrypt_broker_key(request.api_key, self._broker_enc_key)
        doc = {
            "user_id": target_user_id,
            "broker_name": request.broker_name,
            "encrypted_api_key": encrypted,
        }
        await self._db["broker_keys"].replace_one(
            {"user_id": target_user_id, "broker_name": request.broker_name},
            doc,
            upsert=True,
        )
        return BrokerKeyResponse(user_id=target_user_id, broker_name=request.broker_name)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)


def create_app(
    db=None,
    secret_key: Optional[str] = None,
    broker_key_encryption_key: Optional[str] = None,
) -> FastAPI:
    """Create and return the FastAPI application.

    Args:
        db: Async Motor database instance. If None, reads MONGO_URI from env.
        secret_key: JWT signing secret. Falls back to JWT_SECRET_KEY env var.
        broker_key_encryption_key: Fernet key. Falls back to BROKER_KEY_ENCRYPTION_KEY env var.
    """
    _secret_key = secret_key or os.environ.get("JWT_SECRET_KEY", "change-me-in-production")
    _enc_key = broker_key_encryption_key or os.environ.get(
        "BROKER_KEY_ENCRYPTION_KEY", ""
    )

    if db is None:
        import motor.motor_asyncio as motor_asyncio

        mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
        client = motor_asyncio.AsyncIOMotorClient(mongo_uri)
        db = client["agentictrader"]

    service = AuthService(db=db, secret_key=_secret_key, broker_key_encryption_key=_enc_key)

    app = FastAPI(title="Auth Service", version="1.0.0")

    # ------------------------------------------------------------------
    # Dependency: extract current user from Bearer token
    # ------------------------------------------------------------------

    async def get_current_user_dep(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    ) -> UserProfile:
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await service.get_current_user(credentials.credentials)

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.get("/health")
    async def health() -> dict:
        """Liveness check."""
        return {"status": "ok"}

    @app.post("/auth/register", response_model=TokenResponse, status_code=201)
    async def register(request: RegisterRequest) -> TokenResponse:
        """Register a new user and return JWT tokens."""
        return await service.register(request)

    @app.post("/auth/login", response_model=TokenResponse)
    async def login(request: LoginRequest) -> TokenResponse:
        """Authenticate and return JWT tokens."""
        return await service.login(request)

    @app.post("/auth/refresh", response_model=TokenResponse)
    async def refresh(request: RefreshRequest) -> TokenResponse:
        """Exchange a refresh token for a new access token."""
        return await service.refresh(request.refresh_token)

    @app.get("/auth/me", response_model=UserProfile)
    async def get_me(
        current_user: UserProfile = Depends(get_current_user_dep),
    ) -> UserProfile:
        """Return the authenticated user's profile."""
        return current_user

    @app.post(
        "/users/{user_id}/broker-keys",
        response_model=BrokerKeyResponse,
        status_code=201,
    )
    async def store_broker_key(
        user_id: str,
        request: BrokerKeyRequest,
        current_user: UserProfile = Depends(get_current_user_dep),
    ) -> BrokerKeyResponse:
        """Store an encrypted broker API key for a user."""
        return await service.store_broker_key(
            requesting_user_id=current_user.user_id,
            requesting_role=current_user.role,
            target_user_id=user_id,
            request=request,
        )

    return app


# ---------------------------------------------------------------------------
# Entry point — module-level app for `uvicorn services.auth.main:app`
# ---------------------------------------------------------------------------

app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.auth.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("AUTH_SERVICE_PORT", "8007")),
    )
