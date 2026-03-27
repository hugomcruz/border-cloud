import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
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
    list_servers,
    list_snapshots_by_label,
    power_off,
    power_on,
    shutdown_server,
    upsert_ip_rule,
)
from app.models.db import AppConfig, OperationLog, User, VmConfig
from app.vms.schemas import VirtualMachineOut

router = APIRouter(prefix="/vms", tags=["vms"])

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _emit(q: asyncio.Queue, event: dict) -> None:  # type: ignore[type-arg]
    """Serialise an event dict and put it into the operation queue (non-blocking)."""
    q.put_nowait(json.dumps(event))


# --------------------------------------------------------------------------- #
# Background task: archive
# --------------------------------------------------------------------------- #

async def _run_archive(name: str, server_id: int, op_id: str, log_id: int) -> None:
    """Archive a VM: shutdown → snapshot → delete.  Runs as a background asyncio task."""
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
            await shutdown_server(name)
        except Exception as exc:
            log.exception("[archive:%s] shutdown_server failed", name)
            emit({"kind": "error", "message": str(exc), "completedSteps": []})
            if op_log:
                op_log.status = "error"
                await db.commit()
            operations.finish_operation(op_id)
            return
        emit({"kind": "step", "step": {"step": "Shutting down VM", "status": "done"}})

        # Step 2: Create snapshot
        emit({"kind": "step", "step": {"step": "Creating snapshot", "status": "in-progress"}})
        try:
            await create_snapshot(name, server_id)
        except Exception as exc:
            log.exception("[archive:%s] create_snapshot failed", name)
            emit({"kind": "error", "message": str(exc), "completedSteps": ["Shutting down VM"]})
            if op_log:
                op_log.status = "error"
                await db.commit()
            operations.finish_operation(op_id)
            return
        emit({"kind": "step", "step": {"step": "Creating snapshot", "status": "done"}})

        # Step 3: Delete server (only after snapshot succeeded)
        emit({"kind": "step", "step": {"step": "Deleting server", "status": "in-progress"}})
        try:
            await delete_server(server_id)
        except Exception as exc:
            log.exception("[archive:%s] delete_server failed", name)
            emit({"kind": "error", "message": str(exc), "completedSteps": ["Shutting down VM", "Creating snapshot"]})
            if op_log:
                op_log.status = "error"
                await db.commit()
            operations.finish_operation(op_id)
            return
        emit({"kind": "step", "step": {"step": "Deleting server", "status": "done"}})

        # Step 4: Remove DNS record (non-fatal)
        try:
            from app.lib.cloudflare import delete_dns_record
            await delete_dns_record(name, db)
        except Exception as exc:
            log.warning("[archive:%s] delete_dns_record failed: %s", name, exc)
            emit({"kind": "warning", "message": f"DNS record not removed: {exc}"})

        emit({"kind": "complete", "summary": f"VM '{name}' archived successfully."})
        if op_log:
            op_log.status = "done"
            await db.commit()
        log.info("[archive:%s] complete", name)

    operations.finish_operation(op_id)


# --------------------------------------------------------------------------- #
# Background task: delete (no snapshot)
# --------------------------------------------------------------------------- #

async def _run_delete(name: str, op_id: str, log_id: int) -> None:
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
                await delete_dns_record(name, db)
                emit({"kind": "step", "step": {"step": "Removing DNS record", "status": "done"}})
            except Exception as exc:
                log.warning("[delete:%s] delete_dns_record failed: %s", name, exc)
                emit({"kind": "step", "step": {"step": "Removing DNS record", "status": "done"}})
                emit({"kind": "warning", "message": f"DNS record not removed: {exc}"})

        # Step 2: Delete server
        emit({"kind": "step", "step": {"step": "Deleting server", "status": "in-progress"}})
        try:
            await delete_server_by_name(name)
        except Exception as exc:
            log.exception("[delete:%s] delete_server_by_name failed", name)
            emit({"kind": "error", "message": str(exc), "completedSteps": []})
            if op_log:
                op_log.status = "error"
                await db.commit()
            operations.finish_operation(op_id)
            return
        emit({"kind": "step", "step": {"step": "Deleting server", "status": "done"}})

        emit({"kind": "complete", "summary": f"VM '{name}' deleted."})
        if op_log:
            op_log.status = "done"
            await db.commit()
        log.info("[delete:%s] complete", name)

    operations.finish_operation(op_id)


# --------------------------------------------------------------------------- #
# Background task: restore
# --------------------------------------------------------------------------- #

async def _run_restore(name: str, op_id: str, log_id: int) -> None:
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
            snapshots = await list_snapshots_by_label()
        except Exception as exc:
            log.exception("[restore:%s] failed to list snapshots", name)
            emit({"kind": "error", "message": str(exc), "completedSteps": []})
            if op_log:
                op_log.status = "error"
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
            emit({"kind": "error", "message": f"No snapshot found for VM '{name}'.", "completedSteps": []})
            if op_log:
                op_log.status = "error"
                await db.commit()
            operations.finish_operation(op_id)
            return

        latest = vm_snaps[0]
        log.info("[restore:%s] using snapshot id=%s server_type=%s location=%s", name, latest.id, latest.server_type, latest.location)

        preferred_type = latest.server_type or "cx23"
        preferred_location = latest.location or "nbg1"

        app_cfg_result = await db.execute(select(AppConfig))
        app_configs = {row.key: row.value for row in app_cfg_result.scalars().all()}
        ssh_key = app_configs.get("hetzner_default_ssh_key", "")

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
                name, latest.id, preferred_type, preferred_location, ssh_key
            )
            log.info("[restore:%s] server created: %s", name, server_info)
        except Exception as exc:
            log.exception("[restore:%s] create_server_from_snapshot failed", name)
            emit({"kind": "error", "message": str(exc), "completedSteps": []})
            if op_log:
                op_log.status = "error"
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
                await update_a_record(name, public_ip, db)
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

        # Step 3: Update firewall (non-fatal)
        emit({"kind": "step", "step": {"step": "Updating firewall", "status": "in-progress"}})
        try:
            firewall_name = app_configs.get("hetzner_firewall_name", "")
            log.info("[restore:%s] upserting firewall rule: firewall=%r ip=%s", name, firewall_name, public_ip)
            await upsert_ip_rule(firewall_name, public_ip)
            emit({"kind": "step", "step": {"step": "Updating firewall", "status": "done"}})
        except Exception as exc:
            log.warning("[restore:%s] upsert_ip_rule skipped: %s", name, exc)
            emit({"kind": "step", "step": {"step": "Updating firewall", "status": "done"}})
            emit({
                "kind": "warning",
                "message": f"Firewall not updated: {exc}. Set HETZNER_FIREWALL_NAME to enable automatic firewall rules.",
            })

        emit({"kind": "complete", "summary": f"VM '{name}' restored. IP: {public_ip}"})
        if op_log:
            op_log.status = "done"
            await db.commit()
        log.info("[restore:%s] complete. public_ip=%s", name, public_ip)

    operations.finish_operation(op_id)


@router.get("")
async def get_vms(
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return merged list of live and archived VMs."""
    live_vms, snapshots = await asyncio.gather(list_servers(), list_snapshots_by_label())

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
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Delete server without snapshot; returns op_id immediately (202)."""
    op_log = OperationLog(vm_name=name, operation="delete", status="in-progress")
    db.add(op_log)
    await db.commit()
    await db.refresh(op_log)

    op_id, _ = operations.new_operation()
    asyncio.create_task(_run_delete(name, op_id, op_log.id))

    log.info("[delete:%s] started op_id=%s", name, op_id)
    return JSONResponse({"op_id": op_id}, status_code=202)


@router.post("/{name}/start")
async def start_vm(
    name: str,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
) -> JSONResponse:
    await power_on(name)
    return JSONResponse({"status": "running"})


@router.post("/{name}/stop")
async def stop_vm(
    name: str,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
) -> JSONResponse:
    await power_off(name)
    return JSONResponse({"status": "stopped"})


@router.post("/{name}/archive", status_code=202)
async def archive_vm(
    name: str,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Start archive operation in the background; returns op_id immediately (202)."""
    live_vms = await list_servers()
    server = next((v for v in live_vms if v.name == name), None)
    if server is None or server.server_id is None:
        raise HTTPException(status_code=404, detail=f"VM '{name}' not found.")

    op_log = OperationLog(vm_name=name, operation="archive", status="in-progress")
    db.add(op_log)
    await db.commit()
    await db.refresh(op_log)

    op_id, _ = operations.new_operation()
    asyncio.create_task(_run_archive(name, server.server_id, op_id, op_log.id))

    log.info("[archive:%s] started op_id=%s", name, op_id)
    return JSONResponse({"op_id": op_id}, status_code=202)


@router.post("/{name}/restore", status_code=202)
async def restore_vm(
    name: str,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Start restore operation in the background; returns op_id immediately (202)."""
    op_log = OperationLog(vm_name=name, operation="restore", status="in-progress")
    db.add(op_log)
    await db.commit()
    await db.refresh(op_log)

    op_id, _ = operations.new_operation()
    asyncio.create_task(_run_restore(name, op_id, op_log.id))

    log.info("[restore:%s] started op_id=%s", name, op_id)
    return JSONResponse({"op_id": op_id}, status_code=202)


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
