"""Integration tests for GET /ip and POST /firewall/sync — US5."""

from unittest.mock import AsyncMock, patch

import pytest
import respx
from fastapi import HTTPException
from httpx import AsyncClient, Response


@pytest.mark.asyncio
class TestGetIp:
    async def test_get_ip_with_x_forwarded_for_returns_first_ip(
        self, authenticated_client: AsyncClient
    ) -> None:
        resp = await authenticated_client.get(
            "/ip", headers={"X-Forwarded-For": "203.0.113.1, 10.0.0.1"}
        )
        assert resp.status_code == 200
        assert resp.json() == {"ip": "203.0.113.1"}

    async def test_get_ip_without_header_calls_reflection_url(
        self, authenticated_client: AsyncClient
    ) -> None:
        with (
            respx.mock() as mock_http,
            patch("app.lib.ip.settings") as mock_settings,
        ):
            mock_settings.IP_REFLECTION_URL = "https://api.ipify.org?format=json"
            mock_http.get("https://api.ipify.org?format=json").mock(
                return_value=Response(200, json={"ip": "203.0.113.5"})
            )
            resp = await authenticated_client.get("/ip")

        assert resp.status_code == 200
        assert resp.json()["ip"] == "203.0.113.5"

    async def test_get_ip_reflection_failure_returns_503(
        self, authenticated_client: AsyncClient
    ) -> None:
        with (
            respx.mock() as mock_http,
            patch("app.lib.ip.settings") as mock_settings,
        ):
            mock_settings.IP_REFLECTION_URL = "https://api.ipify.org?format=json"
            mock_http.get("https://api.ipify.org?format=json").mock(
                return_value=Response(503, text="down")
            )
            resp = await authenticated_client.get("/ip")

        assert resp.status_code == 503
        assert "Unable to detect" in resp.json().get("detail", "")

    async def test_get_ip_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get("/ip")
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestFirewallSync:
    async def test_sync_valid_ip_returns_already_present_bool(
        self, authenticated_client: AsyncClient
    ) -> None:
        with patch("app.firewall.router.upsert_ip_rule", new_callable=AsyncMock, return_value=False):
            resp = await authenticated_client.post(
                "/firewall/sync", json={"ip": "203.0.113.1"}
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ip"] == "203.0.113.1"
        assert data["alreadyPresent"] is False

    async def test_sync_invalid_ip_returns_400(
        self, authenticated_client: AsyncClient
    ) -> None:
        resp = await authenticated_client.post(
            "/firewall/sync", json={"ip": "not-an-ip"}
        )
        assert resp.status_code == 400

    async def test_sync_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post("/firewall/sync", json={"ip": "1.2.3.4"})
        assert resp.status_code == 401

    async def test_sync_upsert_failure_returns_500(
        self, authenticated_client: AsyncClient
    ) -> None:
        with patch(
            "app.firewall.router.upsert_ip_rule",
            new_callable=AsyncMock,
            side_effect=HTTPException(500, "firewall error"),
        ):
            resp = await authenticated_client.post(
                "/firewall/sync", json={"ip": "203.0.113.1"}
            )
        assert resp.status_code == 500
