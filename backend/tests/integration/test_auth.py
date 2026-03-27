"""Integration tests for /auth/token and /auth/logout routes.

These run against the real test DB (DATABASE_URL_TEST) using the ASGI test client.
Tests are written FIRST (TDD) — they define the contract the implementation must satisfy.

Run: pytest tests/integration/test_auth.py
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_correct_credentials_returns_200_and_cookie(
    client: AsyncClient,
) -> None:
    """POST /auth/token with correct creds → 200 and Set-Cookie with access_token."""
    resp = await client.post(
        "/auth/token", json={"username": "admin", "password": "testpassword"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "access_token" in resp.cookies


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client: AsyncClient) -> None:
    """POST /auth/token with wrong password → 401."""
    resp = await client.post(
        "/auth/token", json={"username": "admin", "password": "wrongpassword"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user_returns_401(client: AsyncClient) -> None:
    """POST /auth/token with unknown username → 401."""
    resp = await client.post(
        "/auth/token", json={"username": "nobody", "password": "testpassword"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_without_cookie_returns_401(client: AsyncClient) -> None:
    """GET /vms without cookie → 401 (requires authentication)."""
    resp = await client.get("/vms")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_returns_200_and_clears_cookie(
    authenticated_client: AsyncClient,
) -> None:
    """POST /auth/logout → 200 and Max-Age=0 cookie."""
    resp = await authenticated_client.post("/auth/logout")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("message") == "Logged out"
    # The cookie should be cleared (value "" and max_age=0)
    set_cookie_header = resp.headers.get("set-cookie", "")
    assert "access_token" in set_cookie_header
    assert "max-age=0" in set_cookie_header.lower()


@pytest.mark.asyncio
async def test_protected_route_after_logout_returns_401(
    authenticated_client: AsyncClient,
) -> None:
    """GET /vms after logout cookie is cleared → 401."""
    await authenticated_client.post("/auth/logout")
    # Manually delete the cookie to simulate browser clearing it
    authenticated_client.cookies.clear()
    resp = await authenticated_client.get("/vms")
    assert resp.status_code == 401
