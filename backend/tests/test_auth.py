import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.routers.auth import _users


@pytest.fixture(autouse=True)
def _clear_users():
    # Disable allowlist for tests so test emails aren't rejected
    original = settings.allowed_emails_str
    settings.allowed_emails_str = ""
    _users.clear()
    yield
    _users.clear()
    settings.allowed_emails_str = original


@pytest.fixture
def client():
    return TestClient(app)


def test_register_and_login(client: TestClient):
    # Register
    res = client.post("/api/auth/register", json={"email": "a@b.com", "password": "test1234"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    assert token

    # Login
    res = client.post("/api/auth/login", json={"email": "a@b.com", "password": "test1234"})
    assert res.status_code == 200
    assert res.json()["access_token"]


def test_login_wrong_password(client: TestClient):
    client.post("/api/auth/register", json={"email": "a@b.com", "password": "test1234"})
    res = client.post("/api/auth/login", json={"email": "a@b.com", "password": "wrongpwd"})
    assert res.status_code == 401


def test_me_requires_auth(client: TestClient):
    res = client.get("/api/auth/me")
    assert res.status_code in (401, 403)


def test_me_with_token(client: TestClient):
    res = client.post("/api/auth/register", json={"email": "a@b.com", "password": "test1234"})
    token = res.json()["access_token"]
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["email"] == "a@b.com"


def test_duplicate_register(client: TestClient):
    client.post("/api/auth/register", json={"email": "a@b.com", "password": "test1234"})
    res = client.post("/api/auth/register", json={"email": "a@b.com", "password": "test4567"})
    assert res.status_code == 409
