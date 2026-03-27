"""Integration tests for config routes — US6."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestVmConfigCrud:
    async def test_list_vm_configs_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get("/config/vm-configs")
        assert resp.status_code == 401

    async def test_create_vm_config_returns_201(
        self, authenticated_client: AsyncClient
    ) -> None:
        resp = await authenticated_client.post(
            "/config/vm-configs",
            json={"vm_name": "test-vm", "domain": "test-vm.example.com"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["vm_name"] == "test-vm"
        assert data["domain"] == "test-vm.example.com"
        assert "id" in data

    async def test_create_vm_config_duplicate_returns_409(
        self, authenticated_client: AsyncClient
    ) -> None:
        # First creation
        await authenticated_client.post(
            "/config/vm-configs",
            json={"vm_name": "dup-vm", "domain": "dup.example.com"},
        )
        # Duplicate
        resp = await authenticated_client.post(
            "/config/vm-configs",
            json={"vm_name": "dup-vm", "domain": "other.example.com"},
        )
        assert resp.status_code == 409

    async def test_update_vm_config_updates_domain(
        self, authenticated_client: AsyncClient
    ) -> None:
        create_resp = await authenticated_client.post(
            "/config/vm-configs",
            json={"vm_name": "update-vm", "domain": "old.example.com"},
        )
        config_id = create_resp.json()["id"]

        update_resp = await authenticated_client.put(
            f"/config/vm-configs/{config_id}",
            json={"domain": "new.example.com"},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["domain"] == "new.example.com"

    async def test_update_vm_config_not_found_returns_404(
        self, authenticated_client: AsyncClient
    ) -> None:
        resp = await authenticated_client.put(
            "/config/vm-configs/99999",
            json={"domain": "new.example.com"},
        )
        assert resp.status_code == 404

    async def test_delete_vm_config_removes_record(
        self, authenticated_client: AsyncClient
    ) -> None:
        create_resp = await authenticated_client.post(
            "/config/vm-configs",
            json={"vm_name": "delete-vm", "domain": "del.example.com"},
        )
        config_id = create_resp.json()["id"]

        del_resp = await authenticated_client.delete(f"/config/vm-configs/{config_id}")
        assert del_resp.status_code == 204

        # Verify it's gone
        list_resp = await authenticated_client.get("/config/vm-configs")
        names = [c["vm_name"] for c in list_resp.json()["vm_configs"]]
        assert "delete-vm" not in names


@pytest.mark.asyncio
class TestAppConfig:
    async def test_list_app_configs_returns_200(
        self, authenticated_client: AsyncClient
    ) -> None:
        resp = await authenticated_client.get("/config/app")
        assert resp.status_code == 200
        assert "app_configs" in resp.json()

    async def test_update_app_config_unauthenticated_returns_401(
        self, client: AsyncClient
    ) -> None:
        resp = await client.put("/config/app/hetzner_default_location", json={"value": "fsn1"})
        assert resp.status_code == 401
