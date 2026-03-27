"""Unit tests for cloudflare.py update_a_record() — T059."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
from fastapi import HTTPException
from httpx import Response


@pytest.mark.asyncio
async def test_update_a_record_success() -> None:
    """update_a_record() performs zone lookup → record lookup → PATCH successfully."""
    mock_db = AsyncMock()
    mock_vm_config = MagicMock()
    mock_vm_config.domain = "web-01.example.com"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=mock_vm_config)
    mock_db.execute = AsyncMock(return_value=mock_result)

    with respx.mock(base_url="https://api.cloudflare.com") as mock_cf:
        mock_cf.get("/client/v4/zones", params={"name": "example.com"}).mock(
            return_value=Response(
                200,
                json={"success": True, "result": [{"id": "zone-abc"}]},
            )
        )
        mock_cf.get(
            "/client/v4/zones/zone-abc/dns_records",
            params={"type": "A", "name": "web-01.example.com"},
        ).mock(
            return_value=Response(
                200,
                json={"success": True, "result": [{"id": "rec-xyz"}]},
            )
        )
        mock_cf.patch("/client/v4/zones/zone-abc/dns_records/rec-xyz").mock(
            return_value=Response(200, json={"success": True})
        )

        with patch("app.config.settings") as mock_settings:
            mock_settings.CLOUDFLARE_API_TOKEN = "fake-token"
            from app.lib.cloudflare import update_a_record
            await update_a_record("web-01", "1.2.3.4", mock_db)


@pytest.mark.asyncio
async def test_update_a_record_raises_502_when_zone_not_found() -> None:
    """update_a_record() raises HTTPException(502) when zone not found."""
    mock_db = AsyncMock()
    mock_vm_config = MagicMock()
    mock_vm_config.domain = "web-01.example.com"
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=mock_vm_config)
    mock_db.execute = AsyncMock(return_value=mock_result)

    with respx.mock(base_url="https://api.cloudflare.com") as mock_cf:
        mock_cf.get("/client/v4/zones", params={"name": "example.com"}).mock(
            return_value=Response(200, json={"success": True, "result": []})
        )

        with patch("app.config.settings") as mock_settings:
            mock_settings.CLOUDFLARE_API_TOKEN = "fake-token"
            from app.lib.cloudflare import update_a_record
            with pytest.raises(HTTPException) as exc_info:
                await update_a_record("web-01", "1.2.3.4", mock_db)

    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_update_a_record_raises_502_when_dns_record_not_found() -> None:
    """update_a_record() raises HTTPException(502) when DNS A record not found."""
    mock_db = AsyncMock()
    mock_vm_config = MagicMock()
    mock_vm_config.domain = "web-01.example.com"
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=mock_vm_config)
    mock_db.execute = AsyncMock(return_value=mock_result)

    with respx.mock(base_url="https://api.cloudflare.com") as mock_cf:
        mock_cf.get("/client/v4/zones", params={"name": "example.com"}).mock(
            return_value=Response(200, json={"success": True, "result": [{"id": "zone-abc"}]})
        )
        mock_cf.get(
            "/client/v4/zones/zone-abc/dns_records",
            params={"type": "A", "name": "web-01.example.com"},
        ).mock(
            return_value=Response(200, json={"success": True, "result": []})
        )

        with patch("app.config.settings") as mock_settings:
            mock_settings.CLOUDFLARE_API_TOKEN = "fake-token"
            from app.lib.cloudflare import update_a_record
            with pytest.raises(HTTPException) as exc_info:
                await update_a_record("web-01", "1.2.3.4", mock_db)

    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_update_a_record_raises_502_when_patch_fails() -> None:
    """update_a_record() raises HTTPException(502) when PATCH returns non-200."""
    mock_db = AsyncMock()
    mock_vm_config = MagicMock()
    mock_vm_config.domain = "web-01.example.com"
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=mock_vm_config)
    mock_db.execute = AsyncMock(return_value=mock_result)

    with respx.mock(base_url="https://api.cloudflare.com") as mock_cf:
        mock_cf.get("/client/v4/zones", params={"name": "example.com"}).mock(
            return_value=Response(200, json={"success": True, "result": [{"id": "zone-abc"}]})
        )
        mock_cf.get(
            "/client/v4/zones/zone-abc/dns_records",
            params={"type": "A", "name": "web-01.example.com"},
        ).mock(
            return_value=Response(200, json={"success": True, "result": [{"id": "rec-xyz"}]})
        )
        mock_cf.patch("/client/v4/zones/zone-abc/dns_records/rec-xyz").mock(
            return_value=Response(500, json={"success": False, "errors": ["Internal Error"]})
        )

        with patch("app.config.settings") as mock_settings:
            mock_settings.CLOUDFLARE_API_TOKEN = "fake-token"
            from app.lib.cloudflare import update_a_record
            with pytest.raises(HTTPException) as exc_info:
                await update_a_record("web-01", "1.2.3.4", mock_db)

    assert exc_info.value.status_code == 502
