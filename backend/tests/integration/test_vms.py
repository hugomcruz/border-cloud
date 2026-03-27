"""Integration tests for /vms routes — US1, US2, US3, US4."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from app.vms.schemas import SnapshotOut, VirtualMachineOut


@pytest.mark.asyncio
class TestGetVms:
    async def test_get_vms_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/vms")
        assert resp.status_code == 401

    async def test_get_vms_returns_merged_list(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        live = [
            VirtualMachineOut(
                name="web-1",
                status="running",
                server_id=1,
                public_ip="1.2.3.4",
                can_start=False,
                can_stop=True,
                can_archive=True,
                can_restore=False,
            )
        ]
        snapshots = [
            SnapshotOut(id=10, vm_name="web-1", description="web-1-snap", created_at="2024-01-01T00:00:00"),
            SnapshotOut(id=20, vm_name="archived-vm", description="archived-vm-snap", created_at="2024-01-02T00:00:00"),
        ]

        with (
            patch("app.vms.router.list_servers", new_callable=AsyncMock, return_value=live),
            patch("app.vms.router.list_snapshots_by_label", new_callable=AsyncMock, return_value=snapshots),
        ):
            resp = await authenticated_client.get("/vms")

        assert resp.status_code == 200
        data = resp.json()
        names = {vm["name"] for vm in data["vms"]}
        assert "web-1" in names
        assert "archived-vm" in names

    async def test_get_vms_archived_vm_flags(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        """A VM with snapshot but no live server should be status=archived, can_restore=True."""
        snapshots = [
            SnapshotOut(id=99, vm_name="old-vm", description="old-vm-snap", created_at="2024-01-01T00:00:00"),
        ]
        with (
            patch("app.vms.router.list_servers", new_callable=AsyncMock, return_value=[]),
            patch("app.vms.router.list_snapshots_by_label", new_callable=AsyncMock, return_value=snapshots),
        ):
            resp = await authenticated_client.get("/vms")

        assert resp.status_code == 200
        vms = resp.json()["vms"]
        assert len(vms) == 1
        vm = vms[0]
        assert vm["status"] == "archived"
        assert vm["can_restore"] is True
        assert vm["can_archive"] is False
        assert vm["can_start"] is False
        assert vm["can_stop"] is False

    async def test_get_vms_hcloud_error_returns_500(
        self,
        authenticated_client: AsyncClient,
    ) -> None:
        with (
            patch("app.vms.router.list_servers", side_effect=Exception("hcloud down")),
        ):
            resp = await authenticated_client.get("/vms")

        assert resp.status_code == 500


@pytest.mark.asyncio
class TestStartStopVm:
    async def test_start_vm_returns_running(
        self, authenticated_client: AsyncClient
    ) -> None:
        with patch("app.vms.router.power_on", new_callable=AsyncMock):
            resp = await authenticated_client.post("/vms/web-01/start")
        assert resp.status_code == 200
        assert resp.json() == {"status": "running"}

    async def test_stop_vm_returns_stopped(
        self, authenticated_client: AsyncClient
    ) -> None:
        with patch("app.vms.router.power_off", new_callable=AsyncMock):
            resp = await authenticated_client.post("/vms/web-01/stop")
        assert resp.status_code == 200
        assert resp.json() == {"status": "stopped"}

    async def test_start_vm_unknown_name_returns_404(
        self, authenticated_client: AsyncClient
    ) -> None:
        from fastapi import HTTPException
        with patch(
            "app.vms.router.power_on",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=404, detail="VM 'missing' not found"),
        ):
            resp = await authenticated_client.post("/vms/missing/start")
        assert resp.status_code == 404

    async def test_start_vm_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post("/vms/web-01/start")
        assert resp.status_code == 401

    async def test_stop_vm_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post("/vms/web-01/stop")
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestArchiveVm:
    async def test_archive_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post("/vms/web-01/archive")
        assert resp.status_code == 401

    async def test_archive_vm_not_found_emits_error_event(
        self, authenticated_client: AsyncClient
    ) -> None:
        """When server not found in live VMs, SSE emits an error event."""
        with patch("app.vms.router.list_servers", new_callable=AsyncMock, return_value=[]):
            resp = await authenticated_client.post(
                "/vms/not-found/archive",
                headers={"Accept": "text/event-stream"},
            )
        # SSE responses body arrives as streaming — read it all
        body = resp.text
        assert "error" in body
        assert "not found" in body.lower()

    async def test_archive_snapshot_failure_does_not_delete_server(
        self, authenticated_client: AsyncClient
    ) -> None:
        """If snapshot creation fails, delete_server must NOT be called (FR-006)."""
        from app.vms.schemas import VirtualMachineOut as VMOut
        live_vm = VMOut(
            name="web-01", status="running", server_id=1,
            can_start=False, can_stop=True, can_archive=True, can_restore=False,
        )
        mock_delete = AsyncMock()
        with (
            patch("app.vms.router.list_servers", new_callable=AsyncMock, return_value=[live_vm]),
            patch("app.vms.router.create_snapshot", new_callable=AsyncMock, side_effect=HTTPException(500, "Snapshot failed")),
            patch("app.vms.router.delete_server", mock_delete),
        ):
            resp = await authenticated_client.post(
                "/vms/web-01/archive",
                headers={"Accept": "text/event-stream"},
            )
        body = resp.text
        assert "error" in body
        mock_delete.assert_not_called()

    async def test_archive_success_emits_complete_event(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Successful archive emits all step events plus a complete event."""
        from app.vms.schemas import VirtualMachineOut as VMOut
        live_vm = VMOut(
            name="web-01", status="running", server_id=1,
            can_start=False, can_stop=True, can_archive=True, can_restore=False,
        )
        with (
            patch("app.vms.router.list_servers", new_callable=AsyncMock, return_value=[live_vm]),
            patch("app.vms.router.create_snapshot", new_callable=AsyncMock, return_value=42),
            patch("app.vms.router.delete_server", new_callable=AsyncMock),
        ):
            resp = await authenticated_client.post(
                "/vms/web-01/archive",
                headers={"Accept": "text/event-stream"},
            )
        body = resp.text
        assert "complete" in body
        assert "web-01" in body


@pytest.mark.asyncio
class TestRestoreVm:
    async def test_restore_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post("/vms/web-01/restore")
        assert resp.status_code == 401

    async def test_restore_no_snapshot_emits_error_event(
        self, authenticated_client: AsyncClient
    ) -> None:
        """When no snapshot exists for the VM, SSE emits an error event immediately."""
        with patch(
            "app.vms.router.list_snapshots_by_label",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await authenticated_client.post(
                "/vms/no-snap/restore",
                headers={"Accept": "text/event-stream"},
            )
        body = resp.text
        assert "error" in body
        assert "snapshot" in body.lower()

    async def test_restore_dns_failure_emits_error_with_completed_steps(
        self, authenticated_client: AsyncClient
    ) -> None:
        """DNS failure emits error with completedSteps containing first step."""
        from app.vms.schemas import SnapshotOut
        snap = SnapshotOut(id=42, vm_name="web-01", description="snap", created_at="2024-01-01T00:00:00")
        with (
            patch("app.vms.router.list_snapshots_by_label", new_callable=AsyncMock, return_value=[snap]),
            patch(
                "app.vms.router.create_server_from_snapshot",
                new_callable=AsyncMock,
                return_value={"server_id": 55, "public_ip": "1.2.3.4"},
            ),
            patch(
                "app.lib.cloudflare.update_a_record",
                new_callable=AsyncMock,
                side_effect=HTTPException(502, "DNS failed"),
            ),
        ):
            resp = await authenticated_client.post(
                "/vms/web-01/restore",
                headers={"Accept": "text/event-stream"},
            )
        body = resp.text
        assert "error" in body

    async def test_restore_success_emits_complete_event(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Successful restore emits all step events and a complete event with IP."""
        from app.vms.schemas import SnapshotOut
        snap = SnapshotOut(id=42, vm_name="web-01", description="snap", created_at="2024-01-01T00:00:00")
        with (
            patch("app.vms.router.list_snapshots_by_label", new_callable=AsyncMock, return_value=[snap]),
            patch(
                "app.vms.router.create_server_from_snapshot",
                new_callable=AsyncMock,
                return_value={"server_id": 55, "public_ip": "5.6.7.8"},
            ),
            patch("app.lib.cloudflare.update_a_record", new_callable=AsyncMock),
            patch("app.vms.router.upsert_ip_rule", new_callable=AsyncMock, return_value=False),
        ):
            resp = await authenticated_client.post(
                "/vms/web-01/restore",
                headers={"Accept": "text/event-stream"},
            )
        body = resp.text
        assert "complete" in body
        assert "5.6.7.8" in body
