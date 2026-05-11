import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.auth.service import get_current_user
from app.database import async_session_factory, get_db
from app.lib import operations
from app.lib.hetzner import (
    create_server_from_snapshot,
    create_snapshot,
    delete_server,
    delete_server_by_name,
    get_server_attachment_config,
    list_servers,
    list_snapshots_by_label,
    power_off,
    power_on,
    prune_old_snapshots,
    remove_ip_rule_by_description,
    shutdown_server,
    upsert_user_ip_rule,
)
from app.models.db import AppConfig, HetznerProject, OperationLog, User, UserProjectPermission, VmArchivedState, VmConfig
from app.vms.schemas import VirtualMachineOut

router = APIRouter(prefix="/vms", tags=["vms"])

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _emit(q: asyncio.Queue, event: dict) -> None:  # type: ignore[type-arg]
    """Serialise an event dict and put it into the operation queue (non-blocking)."""
    q.put_nowait(json.dumps(event))


async def _resolve_project(project_id: int, user: User, db: AsyncSession) -> HetznerProject:
    """Load a HetznerProject and verify the user has access. Raises HTTP errors on failure."""
    result = await db.execute(
        select(HetznerProject).where(
            HetznerProject.id == project_id,
            HetznerProject.is_active == True,  # noqa: E712
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if not user.is_superadmin:
        perm = await db.execute(
            select(UserProjectPermission).where(
                UserProjectPermission.user_id == user.id,
                UserProjectPermission.project_id == project_id,
            )
        )
        if perm.scalar_one_or_none() is None:
            raise HTTPException(status_code=403, detail="Access denied to this project")

    return project


# --------------------------------------------------------------------------- #
# Background task: archive
# --------------------------------------------------------------------------- #

async def _run_archive(name: str, server_id: int, op_id: str, log_id: int, token: str, cloudflare_zone_id: str = "", initiated_by: str = "system", firewall_internal: str = "", cloudflare_api_token: str = "") -> None:
    """Archive a VM: shutdown → snapshot → save state → delete.  Runs as a background asyncio task."""
    q = operations.get_queue(op_id)
    if q is None:
        return  # consumer already gone before we started

    async with async_session_factory() as db:
        op_log = await db.get(OperationLog, log_id)

        def emit(event: dict) -> None:  # type: ignore[type-arg]
            log.debug("[archive:%s] emit %s", name, event)
            _emit(q, event)

        # Step 1: Shut down VM
        emit({"kind": "step", "step": {"step": "Shutting down VM", "status": "in-progress"}})
        try:
            await shutdown_server(name, token)
        except Exception as exc:
            log.exception("[archive:%s] shutdown_server failed", name)
            emit({"kind": "error", "message": str(exc), "completedSteps": []})
            if op_log:
                op_log.status = "error"
                op_log.error_message = str(exc)
                op_log.completed_at = datetime.now(timezone.utc)
                await db.commit()
            operations.finish_operation(op_id)
            return
        emit({"kind": "step", "step": {"step": "Shutting down VM", "status": "done"}})

        # Capture live VM state before deleting (best-effort)
        live_state: dict = {}
        try:
            live_vms = await list_servers(token)
            live = next((v for v in live_vms if v.name == name), None)
            if live:
                live_state = {
                    "server_type": live.server_type,
                    "location": live.location,
                    "public_ip": live.public_ip,
                }
        except Exception:  # noqa: BLE001
            log.warning("[archive:%s] could not capture live VM state", name)

        # Capture attached firewalls and private networks (best-effort)
        attachment_config: dict = {"firewalls": [], "networks": []}
        try:
            attachment_config = await get_server_attachment_config(server_id, token)
            log.info("[archive:%s] captured attachments: %s", name, attachment_config)
        except Exception as exc:  # noqa: BLE001
            log.warning("[archive:%s] could not capture server attachment config: %s", name, exc)

        # Step 2: Create snapshot
        emit({"kind": "step", "step": {"step": "Creating snapshot", "status": "in-progress"}})
        try:
            await create_snapshot(name, server_id, token)
        except Exception as exc:
            log.exception("[archive:%s] create_snapshot failed", name)
            emit({"kind": "error", "message": str(exc), "completedSteps": ["Shutting down VM"]})
            if op_log:
                op_log.status = "error"
                op_log.error_message = str(exc)
                op_log.completed_at = datetime.now(timezone.utc)
                await db.commit()
            operations.finish_operation(op_id)
            return
        emit({"kind": "step", "step": {"step": "Creating snapshot", "status": "done"}})

        # Prune old snapshots — keep only the 3 most recent (including the new one)
        try:
            deleted = await prune_old_snapshots(name, token, keep=3)
            if deleted:
                log.info("[archive:%s] pruned %d old snapshot(s): %s", name, len(deleted), deleted)
        except Exception as exc:  # noqa: BLE001
            log.warning("[archive:%s] snapshot pruning failed (non-fatal): %s", name, exc)

        # Persist archived state to DB
        archived_state = VmArchivedState(
            vm_name=name,
            server_id=server_id,
            server_type=live_state.get("server_type"),
            location=live_state.get("location"),
            public_ip=live_state.get("public_ip"),
            firewalls_json=json.dumps(attachment_config["firewalls"]),
            networks_json=json.dumps(attachment_config["networks"]),
            enable_ipv4=attachment_config.get("enable_ipv4", True),
            enable_ipv6=attachment_config.get("enable_ipv6", True),
        )
        db.add(archived_state)
        await db.commit()
        log.info("[archive:%s] saved archived state: %s", name, live_state)

        # Step 3: Delete server (only after snapshot succeeded)
        emit({"kind": "step", "step": {"step": "Deleting server", "status": "in-progress"}})
        try:
            await delete_server(server_id, token)
        except Exception as exc:
            log.exception("[archive:%s] delete_server failed", name)
            emit({"kind": "error", "message": str(exc), "completedSteps": ["Shutting down VM", "Creating snapshot"]})
            if op_log:
                op_log.status = "error"
                op_log.error_message = str(exc)
                op_log.completed_at = datetime.now(timezone.utc)
                await db.commit()
            operations.finish_operation(op_id)
            return
        emit({"kind": "step", "step": {"step": "Deleting server", "status": "done"}})

        # Remove VM's IP from internal firewall (non-fatal)
        if firewall_internal:
            try:
                await remove_ip_rule_by_description(firewall_internal, token, name)
                log.info("[archive:%s] removed internal firewall rule for VM", name)
            except Exception as exc:  # noqa: BLE001
                log.warning("[archive:%s] internal firewall cleanup failed: %s", name, exc)

        # Step 4: Remove DNS record (non-fatal)
        try:
            from app.lib.cloudflare import delete_dns_record
            await delete_dns_record(name, db, cloudflare_zone_id, cloudflare_api_token)
        except Exception as exc:
            log.warning("[archive:%s] delete_dns_record failed: %s", name, exc)
            emit({"kind": "warning", "message": f"DNS record not removed: {exc}"})

        emit({"kind": "complete", "summary": f"VM '{name}' archived successfully."})
        if op_log:
            op_log.status = "done"
            op_log.completed_at = datetime.now(timezone.utc)
            await db.commit()
        log.info("[archive:%s] complete", name)

    operations.finish_operation(op_id)


# --------------------------------------------------------------------------- #
# Background task: delete (no snapshot)
# --------------------------------------------------------------------------- #

async def _run_delete(name: str, op_id: str, log_id: int, token: str, cloudflare_zone_id: str = "", initiated_by: str = "system", firewall_internal: str = "", cloudflare_api_token: str = "") -> None:
    """Delete a VM immediately without snapshotting. Runs as a background asyncio task."""
    q = operations.get_queue(op_id)
    if q is None:
        return

    async with async_session_factory() as db:
        op_log = await db.get(OperationLog, log_id)

        def emit(event: dict) -> None:  # type: ignore[type-arg]
            log.debug("[delete:%s] emit %s", name, event)
            _emit(q, event)

        # Step 1: Remove DNS record (non-fatal)
        vm_cfg_result = await db.execute(select(VmConfig).where(VmConfig.vm_name == name))
        vm_cfg = vm_cfg_result.scalar_one_or_none()
        if vm_cfg and vm_cfg.domain:
            emit({"kind": "step", "step": {"step": "Removing DNS record", "status": "in-progress"}})
            try:
                from app.lib.cloudflare import delete_dns_record
                await delete_dns_record(name, db, cloudflare_zone_id, cloudflare_api_token)
                emit({"kind": "step", "step": {"step": "Removing DNS record", "status": "done"}})
            except Exception as exc:
                log.warning("[delete:%s] delete_dns_record failed: %s", name, exc)
                emit({"kind": "step", "step": {"step": "Removing DNS record", "status": "done"}})
                emit({"kind": "warning", "message": f"DNS record not removed: {exc}"})

        # Step 2: Delete server
        emit({"kind": "step", "step": {"step": "Deleting server", "status": "in-progress"}})
        try:
            await delete_server_by_name(name, token)
        except Exception as exc:
            log.exception("[delete:%s] delete_server_by_name failed", name)
            emit({"kind": "error", "message": str(exc), "completedSteps": []})
            if op_log:
                op_log.status = "error"
                op_log.error_message = str(exc)
                op_log.completed_at = datetime.now(timezone.utc)
                await db.commit()
            operations.finish_operation(op_id)
            return
        emit({"kind": "step", "step": {"step": "Deleting server", "status": "done"}})

        # Remove VM's IP from internal firewall (non-fatal)
        if firewall_internal:
            try:
                await remove_ip_rule_by_description(firewall_internal, token, name)
                log.info("[delete:%s] removed internal firewall rule for VM", name)
            except Exception as exc:  # noqa: BLE001
                log.warning("[delete:%s] internal firewall cleanup failed: %s", name, exc)

        emit({"kind": "complete", "summary": f"VM '{name}' deleted."})
        if op_log:
            op_log.status = "done"
            op_log.completed_at = datetime.now(timezone.utc)
            await db.commit()
        log.info("[delete:%s] complete", name)

    operations.finish_operation(op_id)


# --------------------------------------------------------------------------- #
# Background task: restore
# --------------------------------------------------------------------------- #

async def _run_restore(name: str, op_id: str, log_id: int, token: str, firewall_name: str, cloudflare_zone_id: str = "", firewall_internal: str = "", initiated_by: str = "system", cloudflare_api_token: str = "") -> None:
    """Restore a VM from snapshot.  Runs as a background asyncio task."""
    q = operations.get_queue(op_id)
    if q is None:
        return

    async with async_session_factory() as db:
        op_log = await db.get(OperationLog, log_id)

        def emit(event: dict) -> None:  # type: ignore[type-arg]
            log.debug("[restore:%s] emit %s", name, event)
            _emit(q, event)

        log.info("[restore:%s] starting", name)

        try:
            snapshots = await list_snapshots_by_label(token)
        except Exception as exc:
            log.exception("[restore:%s] failed to list snapshots", name)
            emit({"kind": "error", "message": str(exc), "completedSteps": []})
            if op_log:
                op_log.status = "error"
                op_log.error_message = str(exc)
                op_log.completed_at = datetime.now(timezone.utc)
                await db.commit()
            operations.finish_operation(op_id)
            return

        vm_snaps = sorted(
            [s for s in snapshots if s.vm_name == name],
            key=lambda s: s.created_at,
            reverse=True,
        )
        log.info("[restore:%s] found %d snapshot(s): %s", name, len(vm_snaps), [(s.id, s.created_at, s.server_type, s.location) for s in vm_snaps])

        if not vm_snaps:
            msg = f"No snapshot found for VM '{name}'."
            emit({"kind": "error", "message": msg, "completedSteps": []})
            if op_log:
                op_log.status = "error"
                op_log.error_message = msg
                op_log.completed_at = datetime.now(timezone.utc)
                await db.commit()
            operations.finish_operation(op_id)
            return

        latest = vm_snaps[0]
        log.info("[restore:%s] using snapshot id=%s server_type=%s location=%s", name, latest.id, latest.server_type, latest.location)

        preferred_type = latest.server_type or "cx23"
        preferred_location = latest.location or "nbg1"

        # Prefer archived state (DB) over snapshot labels for server type + location
        archived_state_result = await db.execute(
            select(VmArchivedState)
            .where(VmArchivedState.vm_name == name)
            .order_by(VmArchivedState.archived_at.desc())
        )
        archived_state = archived_state_result.scalars().first()
        firewall_ids: list[int] = []
        network_ids: list[int] = []
        enable_ipv4: bool = True
        enable_ipv6: bool = True
        if archived_state:
            if archived_state.server_type:
                log.info("[restore:%s] using archived state server_type: %s", name, archived_state.server_type)
                preferred_type = archived_state.server_type
            if archived_state.location:
                log.info("[restore:%s] using archived state location: %s", name, archived_state.location)
                preferred_location = archived_state.location
            try:
                firewall_ids = [int(x) for x in json.loads(archived_state.firewalls_json or "[]")]
            except Exception:  # noqa: BLE001
                pass
            try:
                network_ids = [int(x) for x in json.loads(archived_state.networks_json or "[]")]
            except Exception:  # noqa: BLE001
                pass
            enable_ipv4 = archived_state.enable_ipv4
            enable_ipv6 = archived_state.enable_ipv6
            if firewall_ids:
                log.info("[restore:%s] will attach firewall IDs: %s", name, firewall_ids)
            if network_ids:
                log.info("[restore:%s] will attach network IDs: %s", name, network_ids)
            log.info("[restore:%s] enable_ipv4=%s enable_ipv6=%s", name, enable_ipv4, enable_ipv6)

        app_cfg_result = await db.execute(select(AppConfig))
        app_configs = {row.key: row.value for row in app_cfg_result.scalars().all()}
        ssh_key = app_configs.get("hetzner_default_ssh_key", "")
        # firewall_name comes from the project record (passed as parameter)

        vm_cfg_result = await db.execute(select(VmConfig).where(VmConfig.vm_name == name))
        vm_cfg = vm_cfg_result.scalar_one_or_none()
        if vm_cfg and vm_cfg.preferred_server_type:
            log.info("[restore:%s] vm_config overrides server type: %s -> %s", name, preferred_type, vm_cfg.preferred_server_type)
            preferred_type = vm_cfg.preferred_server_type
        log.info("[restore:%s] preferred_type=%s preferred_location=%s ssh_key=%r", name, preferred_type, preferred_location, ssh_key)

        # Step 1: Create server
        emit({"kind": "step", "step": {"step": "Creating server from snapshot", "status": "in-progress"}})
        try:
            server_info = await create_server_from_snapshot(
                name, latest.id, token, preferred_type, preferred_location, ssh_key,
                firewall_ids or None, network_ids or None, enable_ipv4, enable_ipv6,
            )
            log.info("[restore:%s] server created: %s", name, server_info)
        except Exception as exc:
            log.exception("[restore:%s] create_server_from_snapshot failed", name)
            emit({"kind": "error", "message": str(exc), "completedSteps": []})
            if op_log:
                op_log.status = "error"
                op_log.error_message = str(exc)
                op_log.completed_at = datetime.now(timezone.utc)
                await db.commit()
            operations.finish_operation(op_id)
            return
        emit({"kind": "step", "step": {"step": "Creating server from snapshot", "status": "done"}})

        if server_info.get("upgraded"):
            actual_type = server_info.get("actual_type", preferred_type)
            log.warning("[restore:%s] upgraded from %s to %s", name, preferred_type, actual_type)
            emit({
                "kind": "warning",
                "message": f"'{preferred_type}' was unavailable. VM restored on '{actual_type}' instead.",
            })

        public_ip = server_info["public_ip"]

        # Step 2: Update DNS (skip cleanly if no domain is configured)
        if vm_cfg and vm_cfg.domain:
            emit({"kind": "step", "step": {"step": "Updating DNS", "status": "in-progress"}})
            try:
                from app.lib.cloudflare import update_a_record
                log.info("[restore:%s] updating DNS for ip=%s domain=%s", name, public_ip, vm_cfg.domain)
                await update_a_record(name, public_ip, db, cloudflare_zone_id, cloudflare_api_token)
                emit({"kind": "step", "step": {"step": "Updating DNS", "status": "done"}})
            except Exception as exc:
                log.warning("[restore:%s] update_a_record failed: %s", name, exc)
                emit({"kind": "step", "step": {"step": "Updating DNS", "status": "done"}})
                emit({
                    "kind": "warning",
                    "message": f"DNS update failed: {exc}",
                })
        else:
            log.info("[restore:%s] skipping DNS update (no domain configured in VM settings)", name)

        # Step 3: Update internal firewall — add VM's new IP (non-fatal)
        if firewall_internal:
            emit({"kind": "step", "step": {"step": "Updating internal firewall", "status": "in-progress"}})
            try:
                log.info("[restore:%s] upserting internal firewall rule: firewall=%r ip=%s", name, firewall_internal, public_ip)
                await upsert_user_ip_rule(firewall_internal, public_ip, token, name)
                emit({"kind": "step", "step": {"step": "Updating internal firewall", "status": "done"}})
            except Exception as exc:
                log.warning("[restore:%s] upsert_user_ip_rule (internal fw) skipped: %s", name, exc)
                emit({"kind": "step", "step": {"step": "Updating internal firewall", "status": "done"}})
                emit({
                    "kind": "warning",
                    "message": f"Internal firewall not updated: {exc}",
                })

        emit({"kind": "complete", "summary": f"VM '{name}' restored. IP: {public_ip}"})
        if op_log:
            op_log.status = "done"
            op_log.completed_at = datetime.now(timezone.utc)
            await db.commit()
        log.info("[restore:%s] complete. public_ip=%s", name, public_ip)

    operations.finish_operation(op_id)


@router.get("")
async def get_vms(
    project_id: int = Query(..., description="Hetzner project ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return merged list of live and archived VMs."""
    project = await _resolve_project(project_id, current_user, db)
    token = project.api_token
    live_vms, snapshots = await asyncio.gather(list_servers(token), list_snapshots_by_label(token))

    # Load all VM configs to include domain in each VM entry
    vm_cfg_result = await db.execute(select(VmConfig))
    domain_map: dict[str, str] = {
        row.vm_name: row.domain
        for row in vm_cfg_result.scalars().all()
        if row.domain
    }

    # Build a map of vm_name -> latest snapshot
    snapshot_map: dict[str, object] = {}
    for snap in snapshots:
        existing = snapshot_map.get(snap.vm_name)
        if existing is None or snap.created_at > existing.created_at:  # type: ignore[union-attr]
            snapshot_map[snap.vm_name] = snap

    live_names = {vm.name for vm in live_vms}
    result: list[VirtualMachineOut] = []

    # Enrich live VMs with snapshot info
    for vm in live_vms:
        latest = snapshot_map.get(vm.name)
        result.append(
            VirtualMachineOut(
                name=vm.name,
                status=vm.status,
                server_id=vm.server_id,
                public_ip=vm.public_ip,
                server_type=vm.server_type,
                location=vm.location,
                domain=domain_map.get(vm.name),
                protected=vm.protected,
                latest_snapshot=latest,  # type: ignore[arg-type]
                can_restore=False,
                can_archive=not vm.protected,
                can_start=(vm.status == "stopped") and not vm.protected,
                can_stop=(vm.status == "running") and not vm.protected,
            )
        )

    # Add archived VMs (snapshot exists but no live server)
    for vm_name, snap in snapshot_map.items():
        if vm_name not in live_names:
            result.append(
                VirtualMachineOut(
                    name=vm_name,
                    status="archived",
                    domain=domain_map.get(vm_name),
                    latest_snapshot=snap,  # type: ignore[arg-type]
                    can_restore=True,
                    can_archive=False,
                    can_start=False,
                    can_stop=False,
                )
            )

    return JSONResponse({"vms": [vm.model_dump() for vm in result]})


@router.post("/{name}/delete", status_code=202)
async def delete_vm(
    name: str,
    project_id: int = Query(..., description="Hetzner project ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Delete server without snapshot; returns op_id immediately (202)."""
    project = await _resolve_project(project_id, current_user, db)
    token = project.api_token

    op_log = OperationLog(vm_name=name, operation="delete", status="in-progress", initiated_by=current_user.username)
    db.add(op_log)
    await db.commit()
    await db.refresh(op_log)

    op_id, _ = operations.new_operation()
    asyncio.create_task(_run_delete(name, op_id, op_log.id, token, project.cloudflare_zone_id, current_user.username, project.firewall_internal, project.cloudflare_api_token))

    log.info("[delete:%s] started op_id=%s", name, op_id)
    return JSONResponse({"op_id": op_id}, status_code=202)


@router.post("/{name}/start")
async def start_vm(
    name: str,
    project_id: int = Query(..., description="Hetzner project ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    project = await _resolve_project(project_id, current_user, db)
    now = datetime.now(timezone.utc)
    op_log = OperationLog(
        vm_name=name,
        operation="start",
        status="done",
        initiated_by=current_user.username,
        completed_at=now,
    )
    db.add(op_log)
    await power_on(name, project.api_token)
    # Update internal firewall: add this VM's public IP (non-fatal)
    if project.firewall_internal:
        try:
            live_vms = await list_servers(project.api_token)
            server = next((v for v in live_vms if v.name == name), None)
            if server and server.public_ip:
                await upsert_user_ip_rule(project.firewall_internal, server.public_ip, project.api_token, name)
        except Exception as exc:  # noqa: BLE001
            log.warning("[start:%s] internal firewall update failed: %s", name, exc)
    await db.commit()
    return JSONResponse({"status": "running"})


@router.post("/{name}/stop")
async def stop_vm(
    name: str,
    project_id: int = Query(..., description="Hetzner project ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    project = await _resolve_project(project_id, current_user, db)
    now = datetime.now(timezone.utc)
    op_log = OperationLog(
        vm_name=name,
        operation="stop",
        status="done",
        initiated_by=current_user.username,
        completed_at=now,
    )
    db.add(op_log)
    await power_off(name, project.api_token)
    await db.commit()
    return JSONResponse({"status": "stopped"})


@router.post("/{name}/archive", status_code=202)
async def archive_vm(
    name: str,
    project_id: int = Query(..., description="Hetzner project ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Start archive operation in the background; returns op_id immediately (202)."""
    project = await _resolve_project(project_id, current_user, db)
    token = project.api_token

    live_vms = await list_servers(token)
    server = next((v for v in live_vms if v.name == name), None)
    if server is None or server.server_id is None:
        raise HTTPException(status_code=404, detail=f"VM '{name}' not found.")

    op_log = OperationLog(vm_name=name, operation="archive", status="in-progress", initiated_by=current_user.username)
    db.add(op_log)
    await db.commit()
    await db.refresh(op_log)

    op_id, _ = operations.new_operation()
    asyncio.create_task(_run_archive(name, server.server_id, op_id, op_log.id, token, project.cloudflare_zone_id, current_user.username, project.firewall_internal, project.cloudflare_api_token))

    log.info("[archive:%s] started op_id=%s", name, op_id)
    return JSONResponse({"op_id": op_id}, status_code=202)


@router.post("/{name}/restore", status_code=202)
async def restore_vm(
    name: str,
    project_id: int = Query(..., description="Hetzner project ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Start restore operation in the background; returns op_id immediately (202)."""
    project = await _resolve_project(project_id, current_user, db)
    token = project.api_token

    op_log = OperationLog(vm_name=name, operation="restore", status="in-progress", initiated_by=current_user.username)
    db.add(op_log)
    await db.commit()
    await db.refresh(op_log)

    op_id, _ = operations.new_operation()
    asyncio.create_task(_run_restore(name, op_id, op_log.id, token, project.firewall_name, project.cloudflare_zone_id, project.firewall_internal, current_user.username, project.cloudflare_api_token))

    log.info("[restore:%s] started op_id=%s", name, op_id)
    return JSONResponse({"op_id": op_id}, status_code=202)


@router.get("/{name}/logs")
async def get_vm_logs(
    name: str,
    project_id: int = Query(..., description="Hetzner project ID"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return operation logs for a specific VM (project-access-gated)."""
    await _resolve_project(project_id, current_user, db)  # verifies access

    result = await db.execute(
        select(OperationLog)
        .where(OperationLog.vm_name == name)
        .order_by(OperationLog.started_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    return JSONResponse({
        "logs": [
            {
                "id": row.id,
                "vm_name": row.vm_name,
                "operation": row.operation,
                "status": row.status,
                "initiated_by": row.initiated_by,
                "error_message": row.error_message,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            }
            for row in logs
        ]
    })


@router.get("/operations/{op_id}/stream")
async def operation_stream(
    op_id: str,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
) -> EventSourceResponse:
    """SSE stream for a running background operation.  Reads from its asyncio.Queue."""
    q = operations.get_queue(op_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Operation not found or already completed.")

    async def generator() -> AsyncGenerator[str, None]:
        while True:
            item = await q.get()
            if item is operations.SENTINEL:
                break
            yield item  # type: ignore[misc]

    return EventSourceResponse(generator())
