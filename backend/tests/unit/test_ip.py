"""Unit tests for app/lib/ip.py detect_public_ip() — T069."""

from unittest.mock import MagicMock, patch

import pytest
import respx
from fastapi import HTTPException
from httpx import Response


@pytest.mark.asyncio
async def test_detect_public_ip_uses_x_forwarded_for_header() -> None:
    """detect_public_ip() returns the first IP from X-Forwarded-For when present."""
    mock_request = MagicMock()
    mock_request.headers = {"X-Forwarded-For": "203.0.113.1, 10.0.0.1"}

    from app.lib.ip import detect_public_ip

    ip = await detect_public_ip(mock_request)
    assert ip == "203.0.113.1"


@pytest.mark.asyncio
async def test_detect_public_ip_calls_reflection_url_when_no_header() -> None:
    """detect_public_ip() fetches from IP_REFLECTION_URL when header absent."""
    mock_request = MagicMock()
    mock_request.headers = {}

    with (
        respx.mock() as mock_http,
        patch("app.lib.ip.settings") as mock_settings,
    ):
        mock_settings.IP_REFLECTION_URL = "https://api.ipify.org?format=json"
        mock_http.get("https://api.ipify.org?format=json").mock(
            return_value=Response(200, json={"ip": "203.0.113.42"})
        )

        from app.lib.ip import detect_public_ip

        ip = await detect_public_ip(mock_request)

    assert ip == "203.0.113.42"


@pytest.mark.asyncio
async def test_detect_public_ip_raises_503_on_non_200_response() -> None:
    """detect_public_ip() raises HTTPException(503) when reflection URL returns non-200."""
    mock_request = MagicMock()
    mock_request.headers = {}

    with (
        respx.mock() as mock_http,
        patch("app.lib.ip.settings") as mock_settings,
    ):
        mock_settings.IP_REFLECTION_URL = "https://api.ipify.org?format=json"
        mock_http.get("https://api.ipify.org?format=json").mock(
            return_value=Response(503, text="Service Unavailable")
        )

        from app.lib.ip import detect_public_ip

        with pytest.raises(HTTPException) as exc_info:
            await detect_public_ip(mock_request)

    assert exc_info.value.status_code == 503
    assert "Unable to detect" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_detect_public_ip_raises_503_on_network_timeout() -> None:
    """detect_public_ip() raises HTTPException(503) on network timeout."""
    import httpx

    mock_request = MagicMock()
    mock_request.headers = {}

    with (
        respx.mock() as mock_http,
        patch("app.lib.ip.settings") as mock_settings,
    ):
        mock_settings.IP_REFLECTION_URL = "https://api.ipify.org?format=json"
        mock_http.get("https://api.ipify.org?format=json").mock(
            side_effect=httpx.TimeoutException("timeout")
        )

        from app.lib.ip import detect_public_ip

        with pytest.raises(HTTPException) as exc_info:
            await detect_public_ip(mock_request)

    assert exc_info.value.status_code == 503
