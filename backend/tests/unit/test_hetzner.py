"""Unit tests for hetzner.py list functions.

Tests run FIRST — they must FAIL before the implementation in T036.
Hetzner SDK calls are mocked with unittest.mock so no real API calls are made.

Run: pytest tests/unit/test_hetzner.py
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_list_servers_returns_mapped_vms() -> None:
    """list_servers() returns a list of VirtualMachineOut for live servers."""
    mock_server1 = MagicMock()
    mock_server1.name = "web-01"
    mock_server1.id = 1
    mock_server1.status = "running"
    mock_server1.public_net.ipv4.ip = "1.2.3.4"

    mock_server2 = MagicMock()
    mock_server2.name = "web-02"
    mock_server2.id = 2
    mock_server2.status = "off"
    mock_server2.public_net.ipv4 = None

    with patch("app.lib.hetzner._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.servers.get_all = MagicMock(return_value=[mock_server1, mock_server2])
        mock_get_client.return_value = mock_client

        from app.lib.hetzner import list_servers

        result = await list_servers()

    assert len(result) == 2
    assert result[0].name == "web-01"
    assert result[0].status == "running"
    assert result[0].public_ip == "1.2.3.4"
    assert result[1].name == "web-02"
    assert result[1].status == "stopped"
    assert result[1].public_ip is None


@pytest.mark.asyncio
async def test_list_snapshots_by_label_returns_labeled_snapshots() -> None:
    """list_snapshots_by_label() returns snapshots with the vm-name label."""
    mock_image = MagicMock()
    mock_image.id = 100
    mock_image.description = "snapshot-web-01"
    mock_image.created = "2024-01-01T00:00:00+00:00"
    mock_image.labels = {"vm-name": "web-01"}

    with patch("app.lib.hetzner._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.images.get_all = MagicMock(return_value=[mock_image])
        mock_get_client.return_value = mock_client

        from app.lib.hetzner import list_snapshots_by_label

        result = await list_snapshots_by_label()

    assert len(result) == 1
    assert result[0].id == 100
    assert result[0].vm_name == "web-01"


@pytest.mark.asyncio
async def test_list_servers_raises_500_on_sdk_exception() -> None:
    """list_servers() converts SDK exceptions to HTTPException(500)."""
    with patch("app.lib.hetzner._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.servers.get_all = MagicMock(side_effect=Exception("network error"))
        mock_get_client.return_value = mock_client

        from app.lib.hetzner import list_servers

        with pytest.raises(HTTPException) as exc_info:
            await list_servers()

    assert exc_info.value.status_code == 500
    assert "Unable to reach Hetzner Cloud" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_list_snapshots_returns_empty_list_when_none_labeled() -> None:
    """list_snapshots_by_label() returns [] when no labeled snapshots exist."""
    with patch("app.lib.hetzner._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.images.get_all = MagicMock(return_value=[])
        mock_get_client.return_value = mock_client

        from app.lib.hetzner import list_snapshots_by_label

        result = await list_snapshots_by_label()

    assert result == []


# ---------------------------------------------------------------------------
# T043: Unit tests for power_on() and power_off()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_power_on_calls_sdk_for_existing_server() -> None:
    """power_on() calls server.power_on() when server found by name."""
    mock_server = MagicMock()
    mock_server.power_on = MagicMock(return_value=MagicMock())

    with patch("app.lib.hetzner._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.servers.get_all = MagicMock(return_value=[mock_server])
        mock_get_client.return_value = mock_client

        from app.lib.hetzner import power_on

        await power_on("web-01")

    mock_server.power_on.assert_called_once()


@pytest.mark.asyncio
async def test_power_off_calls_sdk_for_existing_server() -> None:
    """power_off() calls server.shutdown() when server found by name."""
    mock_server = MagicMock()
    mock_server.shutdown = MagicMock(return_value=MagicMock())

    with patch("app.lib.hetzner._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.servers.get_all = MagicMock(return_value=[mock_server])
        mock_get_client.return_value = mock_client

        from app.lib.hetzner import power_off

        await power_off("web-01")

    mock_server.shutdown.assert_called_once()


@pytest.mark.asyncio
async def test_power_on_raises_404_when_server_not_found() -> None:
    """power_on() raises HTTPException(404) when server name not found."""
    with patch("app.lib.hetzner._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.servers.get_all = MagicMock(return_value=[])
        mock_get_client.return_value = mock_client

        from app.lib.hetzner import power_on

        with pytest.raises(HTTPException) as exc_info:
            await power_on("missing-vm")

    assert exc_info.value.status_code == 404
    assert "missing-vm" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_power_off_raises_404_when_server_not_found() -> None:
    """power_off() raises HTTPException(404) when server name not found."""
    with patch("app.lib.hetzner._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.servers.get_all = MagicMock(return_value=[])
        mock_get_client.return_value = mock_client

        from app.lib.hetzner import power_off

        with pytest.raises(HTTPException) as exc_info:
            await power_off("gone-vm")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_power_on_raises_500_on_sdk_exception() -> None:
    """power_on() raises HTTPException(500) when SDK throws unexpectedly."""
    with patch("app.lib.hetzner._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.servers.get_all = MagicMock(side_effect=Exception("connection refused"))
        mock_get_client.return_value = mock_client

        from app.lib.hetzner import power_on

        with pytest.raises(HTTPException) as exc_info:
            await power_on("web-01")

    assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# T050: Unit tests for create_snapshot() and delete_server()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_snapshot_calls_sdk_with_vm_name_label() -> None:
    """create_snapshot() calls SDK with labels={'vm-name': name}."""
    mock_server = MagicMock()
    mock_action = MagicMock()
    mock_action.wait_until_finished = MagicMock(return_value=None)
    mock_image = MagicMock()
    mock_image.id = 42
    mock_response = MagicMock()
    mock_response.action = mock_action
    mock_response.image = mock_image

    with patch("app.lib.hetzner._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.servers.get_all = MagicMock(return_value=[mock_server])
        mock_client.servers.create_image = MagicMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        from app.lib.hetzner import create_snapshot

        result = await create_snapshot("web-01", 1)

    assert result == 42
    call_kwargs = mock_client.servers.create_image.call_args
    assert call_kwargs.kwargs.get("labels") == {"vm-name": "web-01"}


@pytest.mark.asyncio
async def test_create_snapshot_raises_500_on_sdk_exception() -> None:
    """create_snapshot() raises HTTPException(500) when SDK throws."""
    with patch("app.lib.hetzner._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.servers.get_all = MagicMock(side_effect=Exception("nework error"))
        mock_get_client.return_value = mock_client

        from app.lib.hetzner import create_snapshot

        with pytest.raises(HTTPException) as exc_info:
            await create_snapshot("web-01", 1)

    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_delete_server_calls_sdk_successfully() -> None:
    """delete_server() resolves server by ID and calls servers.delete()."""
    mock_server = MagicMock()

    with patch("app.lib.hetzner._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.servers.get_by_id = MagicMock(return_value=mock_server)
        mock_client.servers.delete = MagicMock(return_value=None)
        mock_get_client.return_value = mock_client

        from app.lib.hetzner import delete_server

        await delete_server(99)

    mock_client.servers.delete.assert_called_once_with(mock_server)


@pytest.mark.asyncio
async def test_delete_server_raises_500_on_sdk_exception() -> None:
    """delete_server() raises HTTPException(500) when SDK throws."""
    with patch("app.lib.hetzner._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.servers.get_by_id = MagicMock(side_effect=Exception("timeout"))
        mock_get_client.return_value = mock_client

        from app.lib.hetzner import delete_server

        with pytest.raises(HTTPException) as exc_info:
            await delete_server(99)

    assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# T058: Unit tests for create_server_from_snapshot()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_server_from_snapshot_returns_server_id_and_ip() -> None:
    """create_server_from_snapshot() polls until IP assigned and returns dict."""
    mock_created_server = MagicMock()
    mock_created_server.id = 55

    mock_refreshed = MagicMock()
    mock_refreshed.id = 55
    mock_refreshed.public_net.ipv4.ip = "5.6.7.8"

    mock_response = MagicMock()
    mock_response.server = mock_created_server

    with patch("app.lib.hetzner._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.servers.create = MagicMock(return_value=mock_response)
        mock_client.servers.get_by_id = MagicMock(return_value=mock_refreshed)
        mock_get_client.return_value = mock_client

        from app.lib.hetzner import create_server_from_snapshot

        result = await create_server_from_snapshot("web-01", 42, "cx22", "nbg1", "my-key")

    assert result["server_id"] == 55
    assert result["public_ip"] == "5.6.7.8"


@pytest.mark.asyncio
async def test_create_server_from_snapshot_raises_500_on_sdk_exception() -> None:
    """create_server_from_snapshot() raises HTTPException(500) on SDK error."""
    with patch("app.lib.hetzner._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.servers.create = MagicMock(side_effect=Exception("quota exceeded"))
        mock_get_client.return_value = mock_client

        from app.lib.hetzner import create_server_from_snapshot

        with pytest.raises(HTTPException) as exc_info:
            await create_server_from_snapshot("web-01", 42, "cx22", "nbg1", "key")

    assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# T060: Unit tests for upsert_ip_rule()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upsert_ip_rule_returns_true_when_ip_already_present() -> None:
    """upsert_ip_rule() returns True and skips setRules if IP already in source_ips."""
    from hcloud.firewalls.domain import FirewallRule

    existing_rule = MagicMock(spec=FirewallRule)
    existing_rule.direction = "in"
    existing_rule.source_ips = ["1.2.3.4/32", "9.9.9.9/32"]

    mock_firewall = MagicMock()
    mock_firewall.rules = [existing_rule]

    with patch("app.lib.hetzner._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.firewalls.get_all = MagicMock(return_value=[mock_firewall])
        mock_get_client.return_value = mock_client

        from app.lib.hetzner import upsert_ip_rule

        result = await upsert_ip_rule("my-fw", "1.2.3.4")

    assert result is True
    mock_client.firewalls.set_rules.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_ip_rule_appends_rule_when_ip_not_present() -> None:
    """upsert_ip_rule() appends new rule and calls set_rules if IP missing."""
    from hcloud.firewalls.domain import FirewallRule

    existing_rule = MagicMock(spec=FirewallRule)
    existing_rule.direction = "in"
    existing_rule.source_ips = ["9.9.9.9/32"]

    mock_firewall = MagicMock()
    mock_firewall.rules = [existing_rule]

    with patch("app.lib.hetzner._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.firewalls.get_all = MagicMock(return_value=[mock_firewall])
        mock_client.firewalls.set_rules = MagicMock(return_value=None)
        mock_get_client.return_value = mock_client

        from app.lib.hetzner import upsert_ip_rule

        result = await upsert_ip_rule("my-fw", "1.2.3.4")

    assert result is False
    mock_client.firewalls.set_rules.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_ip_rule_raises_404_when_firewall_not_found() -> None:
    """upsert_ip_rule() raises HTTPException(404) when firewall name not found."""
    with patch("app.lib.hetzner._get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.firewalls.get_all = MagicMock(return_value=[])
        mock_get_client.return_value = mock_client

        from app.lib.hetzner import upsert_ip_rule

        with pytest.raises(HTTPException) as exc_info:
            await upsert_ip_rule("missing-fw", "1.2.3.4")

    assert exc_info.value.status_code == 404
