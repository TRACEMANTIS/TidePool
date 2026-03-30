"""Tests for authentication endpoints: login, registration, API keys, password management."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.api_key import ApiKey
from app.utils.security import hash_password, verify_password


# ---------------------------------------------------------------------------
# User registration
# ---------------------------------------------------------------------------


class TestRegistration:
    """Tests for POST /api/v1/auth/register."""

    async def test_register_user(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
    ):
        """Registering with valid data creates a user and returns 201."""
        payload = {
            "username": "newuser",
            "email": "newuser@example.test",
            "password": "Str0ng!P@ssword99",
            "full_name": "New User",
            "is_admin": False,
        }
        resp = await client.post(
            "/api/v1/auth/register",
            json=payload,
            headers=auth_headers,
        )
        assert resp.status_code == 201

        body = resp.json()
        assert body["username"] == "newuser"
        assert body["email"] == "newuser@example.test"
        assert body["full_name"] == "New User"
        assert body["is_admin"] is False
        assert "id" in body
        assert "created_at" in body

        # Verify the user actually exists in the database.
        result = await db_session.execute(
            select(User).where(User.username == "newuser")
        )
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.email == "newuser@example.test"
        # Password should be hashed, not stored as plaintext.
        assert user.hashed_password != "Str0ng!P@ssword99"
        assert verify_password("Str0ng!P@ssword99", user.hashed_password)

    async def test_register_duplicate_username(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Attempting to register with an existing username returns 409."""
        payload = {
            "username": "dupuser",
            "email": "dup1@example.test",
            "password": "Str0ng!P@ssword99",
        }
        resp1 = await client.post(
            "/api/v1/auth/register", json=payload, headers=auth_headers
        )
        assert resp1.status_code == 201

        # Same username, different email.
        payload2 = {
            "username": "dupuser",
            "email": "dup2@example.test",
            "password": "Str0ng!P@ssword99",
        }
        resp2 = await client.post(
            "/api/v1/auth/register", json=payload2, headers=auth_headers
        )
        assert resp2.status_code == 409
        assert "already exists" in resp2.json()["detail"].lower()

    async def test_register_weak_password(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """A password that fails complexity checks returns 422 with error details."""
        payload = {
            "username": "weakpwuser",
            "email": "weakpw@example.test",
            "password": "short",  # Too short, missing complexity requirements.
        }
        resp = await client.post(
            "/api/v1/auth/register", json=payload, headers=auth_headers
        )
        assert resp.status_code == 422

    async def test_register_requires_admin(
        self,
        client: AsyncClient,
        user_headers: dict,
    ):
        """Non-admin users cannot register new accounts."""
        payload = {
            "username": "sneakyuser",
            "email": "sneaky@example.test",
            "password": "Str0ng!P@ssword99",
        }
        resp = await client.post(
            "/api/v1/auth/register", json=payload, headers=user_headers
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class TestLogin:
    """Tests for POST /api/v1/auth/login."""

    async def test_login_success(
        self,
        client: AsyncClient,
        admin_user: User,
    ):
        """Valid credentials return an access token and a refresh token."""
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "testadmin", "password": "Adm!nP@ss2026w0rd"},
        )
        assert resp.status_code == 200

        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        # Tokens should be non-empty JWTs (header.payload.signature).
        assert body["access_token"].count(".") == 2
        assert body["refresh_token"].count(".") == 2

    async def test_login_wrong_password(
        self,
        client: AsyncClient,
        admin_user: User,
    ):
        """Invalid password returns 401 with a generic error message."""
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "testadmin", "password": "wrong_password"},
        )
        assert resp.status_code == 401
        assert "invalid" in resp.json()["detail"].lower()

    async def test_login_nonexistent_user(
        self,
        client: AsyncClient,
    ):
        """Login with a nonexistent username returns 401."""
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "ghost", "password": "anything"},
        )
        assert resp.status_code == 401

    async def test_login_lockout(
        self,
        client: AsyncClient,
        admin_user: User,
        db_session: AsyncSession,
    ):
        """After 5 failed login attempts the account is locked (423)."""
        for i in range(5):
            resp = await client.post(
                "/api/v1/auth/login",
                json={"username": "testadmin", "password": f"wrong_{i}"},
            )
            assert resp.status_code == 401, f"Attempt {i+1} should be 401"

        # The 6th attempt should hit the lockout.
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "testadmin", "password": "wrong_5"},
        )
        assert resp.status_code == 423
        assert "locked" in resp.json()["detail"].lower()

        # Verify the DB state reflects the lockout.
        await db_session.refresh(admin_user)
        assert admin_user.failed_login_attempts >= 5
        assert admin_user.locked_until is not None


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


class TestTokenRefresh:
    """Tests for POST /api/v1/auth/refresh."""

    async def test_refresh_token(
        self,
        client: AsyncClient,
        admin_user: User,
    ):
        """A valid refresh token returns new access and refresh tokens."""
        # First, log in to get tokens.
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "testadmin", "password": "Adm!nP@ss2026w0rd"},
        )
        tokens = login_resp.json()

        # Now refresh.
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert resp.status_code == 200

        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        # New tokens should differ from the originals.
        assert body["access_token"] != tokens["access_token"]

    async def test_refresh_invalid_token(self, client: AsyncClient):
        """An invalid refresh token returns 401."""
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "not.a.valid.jwt"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


class TestApiKeys:
    """Tests for API key CRUD endpoints."""

    async def test_create_api_key(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Creating an API key returns the raw key exactly once."""
        resp = await client.post(
            "/api/v1/auth/api-keys",
            json={"name": "ci-key", "scopes": ["campaigns:read"]},
            headers=auth_headers,
        )
        assert resp.status_code == 201

        body = resp.json()
        assert "raw_key" in body
        assert body["raw_key"].startswith("tp_")
        assert body["name"] == "ci-key"
        assert body["scopes"] == ["campaigns:read"]
        assert body["is_active"] is True

    async def test_api_key_auth(
        self,
        client: AsyncClient,
        api_key_headers: dict,
    ):
        """Requests with a valid X-API-Key header are authenticated."""
        resp = await client.get(
            "/api/v1/auth/me",
            headers=api_key_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "testadmin"

    async def test_api_key_revoke(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        admin_user: User,
    ):
        """Revoking an API key deactivates it; subsequent requests fail."""
        # Create a key.
        create_resp = await client.post(
            "/api/v1/auth/api-keys",
            json={"name": "revoke-test"},
            headers=auth_headers,
        )
        key_data = create_resp.json()
        key_id = key_data["id"]
        raw_key = key_data["raw_key"]

        # Verify it works.
        me_resp = await client.get(
            "/api/v1/auth/me",
            headers={"X-API-Key": raw_key},
        )
        assert me_resp.status_code == 200

        # Revoke it.
        revoke_resp = await client.delete(
            f"/api/v1/auth/api-keys/{key_id}",
            headers=auth_headers,
        )
        assert revoke_resp.status_code == 204

        # Verify it no longer works.
        me_resp2 = await client.get(
            "/api/v1/auth/me",
            headers={"X-API-Key": raw_key},
        )
        assert me_resp2.status_code == 401

    async def test_api_key_scopes(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """A scoped API key can only access allowed endpoints."""
        # Create a key with limited scopes.
        create_resp = await client.post(
            "/api/v1/auth/api-keys",
            json={"name": "scoped-key", "scopes": ["reports:read"]},
            headers=auth_headers,
        )
        key_data = create_resp.json()
        scoped_headers = {"X-API-Key": key_data["raw_key"]}

        # The key should authenticate (GET /auth/me works for any valid key).
        me_resp = await client.get("/api/v1/auth/me", headers=scoped_headers)
        assert me_resp.status_code == 200


# ---------------------------------------------------------------------------
# Password change
# ---------------------------------------------------------------------------


class TestChangePassword:
    """Tests for POST /api/v1/auth/change-password."""

    async def test_change_password(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        admin_user: User,
    ):
        """Changing password with correct current password succeeds."""
        resp = await client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "Adm!nP@ss2026w0rd",
                "new_password": "N3wStr0ng!P@ss2026",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 204

        # Verify the new password works.
        await db_session.refresh(admin_user)
        assert verify_password("N3wStr0ng!P@ss2026", admin_user.hashed_password)
        # Old password should no longer work.
        assert not verify_password("Adm!nP@ss2026w0rd", admin_user.hashed_password)

    async def test_change_password_wrong_current(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Providing an incorrect current password returns 401."""
        resp = await client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "not_my_password",
                "new_password": "N3wStr0ng!P@ss2026",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 401

    async def test_change_password_weak_new(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """A new password that fails complexity validation returns 422."""
        resp = await client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "Adm!nP@ss2026w0rd",
                "new_password": "weak",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422
