import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.security import create_access_token
from app.main import app
from app.services import allowlist


@pytest.fixture(autouse=True)
def _reset_allowlist():
    allowlist.clear()
    yield
    allowlist.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_token():
    """Create a token for an admin user."""
    admin_email = "admin@test.com"
    original = settings.admin_emails_str
    settings.admin_emails_str = admin_email
    token = create_access_token(admin_email)
    yield token
    settings.admin_emails_str = original


@pytest.fixture
def admin_headers(admin_token: str):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def non_admin_token():
    """Create a token for a non-admin user."""
    return create_access_token("user@test.com")


@pytest.fixture
def non_admin_headers(non_admin_token: str):
    return {"Authorization": f"Bearer {non_admin_token}"}


def test_list_allowlist_empty(client: TestClient, admin_headers: dict):
    res = client.get("/api/admin/allowlist", headers=admin_headers)
    assert res.status_code == 200
    assert res.json() == {"emails": []}


def test_add_emails(client: TestClient, admin_headers: dict):
    res = client.post(
        "/api/admin/allowlist",
        json={"emails": ["alice@example.com", "bob@example.com"]},
        headers=admin_headers,
    )
    assert res.status_code == 200
    assert sorted(res.json()["emails"]) == ["alice@example.com", "bob@example.com"]


def test_remove_email(client: TestClient, admin_headers: dict):
    client.post(
        "/api/admin/allowlist",
        json={"emails": ["alice@example.com", "bob@example.com"]},
        headers=admin_headers,
    )
    res = client.delete("/api/admin/allowlist/alice@example.com", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["emails"] == ["bob@example.com"]


def test_remove_nonexistent_email(client: TestClient, admin_headers: dict):
    res = client.delete("/api/admin/allowlist/nobody@example.com", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["emails"] == []


def test_non_admin_cannot_list(client: TestClient, non_admin_headers: dict):
    res = client.get("/api/admin/allowlist", headers=non_admin_headers)
    assert res.status_code == 403


def test_non_admin_cannot_add(client: TestClient, non_admin_headers: dict):
    res = client.post(
        "/api/admin/allowlist",
        json={"emails": ["alice@example.com"]},
        headers=non_admin_headers,
    )
    assert res.status_code == 403


def test_non_admin_cannot_remove(client: TestClient, non_admin_headers: dict):
    res = client.delete("/api/admin/allowlist/a@b.com", headers=non_admin_headers)
    assert res.status_code == 403


def test_unauthenticated_cannot_access(client: TestClient):
    res = client.get("/api/admin/allowlist")
    assert res.status_code in (401, 403)


def test_add_email_normalizes_case(client: TestClient, admin_headers: dict):
    res = client.post(
        "/api/admin/allowlist",
        json={"emails": ["Alice@Example.COM"]},
        headers=admin_headers,
    )
    assert res.status_code == 200
    assert res.json()["emails"] == ["alice@example.com"]


def test_allowlist_integration_with_auth(client: TestClient, admin_headers: dict):
    """Adding an email to the allowlist should allow that user to register."""
    from app.routers.auth import _users

    _users.clear()

    # Set up allowlist with only one email
    client.post(
        "/api/admin/allowlist",
        json={"emails": ["allowed@test.com"]},
        headers=admin_headers,
    )

    # Allowed email can register
    res = client.post(
        "/api/auth/register",
        json={"email": "allowed@test.com", "password": "test1234"},
    )
    assert res.status_code == 200

    # Non-allowed email is rejected
    res = client.post(
        "/api/auth/register",
        json={"email": "blocked@test.com", "password": "test1234"},
    )
    assert res.status_code == 403

    _users.clear()
