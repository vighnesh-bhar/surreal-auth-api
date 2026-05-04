"""Unit tests for /auth routes: register, login, refresh, me."""

import pytest

REGULAR_USER = {"id": "user1", "email": "user@test.com", "role": "user", "is_active": True, "name": "Regular User"}


# ── /auth/register ────────────────────────────────────────────────────────────


def test_register_success(client, mock_db):
    mock_db.query.return_value = []  # no existing user
    mock_db.create.return_value = {"id": "user1", "email": "new@test.com", "role": "user"}

    resp = client.post("/api/v1/auth/register", json={
        "email": "new@test.com",
        "password": "pass1234",
        "name": "New User",
        "role": "user",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_register_duplicate_email_returns_409(client, mock_db):
    mock_db.query.return_value = [{"id": "existing"}]  # email taken

    resp = client.post("/api/v1/auth/register", json={
        "email": "taken@test.com",
        "password": "pass1234",
        "name": "User",
        "role": "user",
    })
    assert resp.status_code == 409


# ── /auth/login ───────────────────────────────────────────────────────────────


def test_login_success(client, mock_db):
    from app.core.auth import hash_password
    pw_hash = hash_password("correctpass")
    mock_db.query.return_value = [{
        "id": "user:user1",
        "email": "test@test.com",
        "password_hash": pw_hash,
        "role": "user",
        "is_active": True,
    }]

    resp = client.post("/api/v1/auth/login", json={
        "email": "test@test.com",
        "password": "correctpass",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_user_not_found_returns_401(client, mock_db):
    mock_db.query.return_value = []

    resp = client.post("/api/v1/auth/login", json={
        "email": "ghost@test.com",
        "password": "pass",
    })
    assert resp.status_code == 401


def test_login_wrong_password_returns_401(client, mock_db):
    from app.core.auth import hash_password
    mock_db.query.return_value = [{
        "id": "user:u1",
        "email": "user@test.com",
        "password_hash": hash_password("correct"),
        "role": "user",
        "is_active": True,
    }]

    resp = client.post("/api/v1/auth/login", json={
        "email": "user@test.com",
        "password": "wrong",
    })
    assert resp.status_code == 401


def test_login_inactive_account_returns_403(client, mock_db):
    from app.core.auth import hash_password
    mock_db.query.return_value = [{
        "id": "user:u1",
        "email": "user@test.com",
        "password_hash": hash_password("pass"),
        "role": "user",
        "is_active": False,
    }]

    resp = client.post("/api/v1/auth/login", json={
        "email": "user@test.com",
        "password": "pass",
    })
    assert resp.status_code == 403


# ── /auth/refresh ─────────────────────────────────────────────────────────────


def test_refresh_token_success(client, mock_db):
    from app.core.auth import create_refresh_token
    from app.services.auth_service import hash_token

    token = create_refresh_token("user1")
    mock_db.query.return_value = [
        {
            "id": "sess1",
            "revoked": False,
            "refresh_token_hash": hash_token(token),
            "user_id": "user1",
        }
    ]

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    mock_db.update.assert_called()
    assert mock_db.create.call_count >= 1


def test_refresh_token_invalid_returns_401(client, mock_db):
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "bad.token.here"})
    assert resp.status_code == 401


def test_refresh_access_token_as_refresh_returns_401(client, mock_db):
    from app.core.auth import create_access_token
    token = create_access_token("user1")

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    assert resp.status_code == 401


def test_refresh_user_not_found_returns_401(client, mock_db):
    from app.core.auth import create_refresh_token
    token = create_refresh_token("ghost")
    mock_db.query.return_value = []

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    assert resp.status_code == 401


# ── /auth/me ──────────────────────────────────────────────────────────────────


def test_me_returns_user_without_password_hash(user_client, mock_db):
    resp = user_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert "password_hash" not in data
    assert "password" not in data
    assert data["email"] == REGULAR_USER["email"]
