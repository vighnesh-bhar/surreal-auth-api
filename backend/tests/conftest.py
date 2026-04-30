import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture()
def mock_db():
    db = AsyncMock()
    # Common async methods expected by routers/services
    db.query = AsyncMock(return_value=[])
    db.query_all = AsyncMock(return_value=[[]])
    db.create = AsyncMock(return_value={})
    db.select_one = AsyncMock(return_value=None)
    db.select_all = AsyncMock(return_value=[])
    db.update = AsyncMock(return_value={})
    db.delete = AsyncMock(return_value=True)
    db.exists = AsyncMock(return_value=False)
    db.count = AsyncMock(return_value=0)
    return db


@pytest.fixture()
def client(monkeypatch, mock_db):
    import app.main as main_mod
    from app.main import app
    from app.db.surreal import get_db
    from app.core import auth as core_auth

    async def _noop():
        return None

    # Prevent real DB connect/disconnect during tests
    monkeypatch.setattr(main_mod, "connect_db", _noop)
    monkeypatch.setattr(main_mod, "disconnect_db", _noop)

    async def _override_get_db():
        return mock_db

    # Default unauthenticated client
    app.dependency_overrides[get_db] = _override_get_db
    # Ensure optional_user doesn't try to decode real tokens in unauthenticated tests
    app.dependency_overrides[core_auth.optional_user] = lambda: None

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture()
def user_client(client, monkeypatch):
    from app.main import app
    from app.core.auth import get_current_user

    user = {
        "id": "user1",
        "email": "user@test.com",
        "role": "user",
        "is_active": True,
        "name": "Regular User",
        "password_hash": "x",
    }

    async def _override_current_user():
        return user

    app.dependency_overrides[get_current_user] = _override_current_user
    return client


@pytest.fixture()
def admin_client(client, monkeypatch):
    from app.main import app
    from app.core.auth import get_current_admin, get_current_user

    admin = {
        "id": "admin1",
        "email": "admin@test.com",
        "role": "admin",
        "is_active": True,
        "name": "Admin",
        "password_hash": "x",
    }

    async def _override_current_admin():
        return admin

    app.dependency_overrides[get_current_admin] = _override_current_admin
    app.dependency_overrides[get_current_user] = _override_current_admin
    return client
