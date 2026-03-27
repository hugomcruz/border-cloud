"""Hetzner Cloud SDK wrapper functions.

All SDK calls are wrapped with asyncio.to_thread() so they run in a thread pool
and don't block the FastAPI async event loop.
"""
import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)

from fastapi import HTTPException
from hcloud import Client
from hcloud.images.domain import Image

from app.settings import settings
from app.vms.schemas import SnapshotOut, VirtualMachineOut


def _get_client() -> Client:
    """Return a configured hcloud Client. Extracted for testability."""
    return Client(token=settings.HETZNER_API_TOKEN)


async def _poll_action(client: Client, action: Any, poll_interval: float = 10.0) -> None:
    """Async-friendly replacement for action.wait_until_finished.

    Polls the action status every `poll_interval` seconds using asyncio.sleep
    so the event loop is never blocked.  No hardcoded timeout — keeps polling
    until Hetzner reports success or error (important for slow operations like
    Windows VM snapshots).
    """
    while True:
        fresh = await asyncio.to_thread(client.actions.get_by_id, action.id)
        if fresh.status == "success":
            return
        if fresh.status == "error":
            error_info = getattr(fresh, "error", {}) or {}
            raise HTTPException(
                status_code=500,
                detail=f"Hetzner action '{fresh.command}' failed: {error_info}",
            )
        log.debug("[hetzner] action %s (%s) progress=%s%% — waiting", fresh.id, fresh.command, fresh.progress)
        await asyncio.sleep(poll_interval)


# Server-type upgrade ladder using current Hetzner type names (as of 2025).
# Deprecated types (cx11/21/31/41, cx22/32/42/52) map to the current x3 line.
# Current Intel: cx23 < cx33 < cx43 < cx53
# Current ARM64: cax11 < cax21 < cax31 < cax41
# Current AMD shared: cpx11 < cpx21 < cpx31 < cpx41 < cpx51
_UPGRADE_PATHS: dict[str, list[str]] = {
    # Old deprecated Intel (cx1x) → current x3
    "cx11": ["cx23", "cx33", "cx43", "cx53"],
    "cx21": ["cx33", "cx43", "cx53"],
    "cx31": ["cx43", "cx53"],
    "cx41": ["cx53"],
    # Old deprecated Intel (cx2x) → current x3
    "cx22": ["cx23", "cx33", "cx43", "cx53"],
    "cx32": ["cx33", "cx43", "cx53"],
    "cx42": ["cx43", "cx53"],
    "cx52": ["cx53"],
    # Current Intel CX line (x3 generation)
    "cx23": ["cx33", "cx43", "cx53"],
    "cx33": ["cx43", "cx53"],
    "cx43": ["cx53"],
    # ARM64 CAX line
    "cax11": ["cax21", "cax31", "cax41"],
    "cax21": ["cax31", "cax41"],
    "cax31": ["cax41"],
    # Shared AMD CPX line
    "cpx11": ["cpx21", "cpx31", "cpx41", "cpx51"],
    "cpx21": ["cpx31", "cpx41", "cpx51"],
    "cpx31": ["cpx41", "cpx51"],
    "cpx41": ["cpx51"],
}
_FALLBACK_LOCATIONS = ["nbg1", "hel1", "fsn1"]


# --------------------------------------------------------------------------- #
# US1 — List servers and snapshots
# --------------------------------------------------------------------------- #


async def list_servers() -> list[VirtualMachineOut]:
    """Return all live Hetzner servers mapped to VirtualMachineOut."""
    try:
        client = _get_client()
        servers: list[Any] = await asyncio.to_thread(client.servers.get_all)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to reach Hetzner Cloud. Please try again.",
        ) from exc

    result: list[VirtualMachineOut] = []
    for server in servers:
        status = "running" if server.status == "running" else "stopped"
        if status == "running" and "hide" in server.labels:
            continue
        public_ip: str | None = None
        if server.public_net.ipv4:
            public_ip = server.public_net.ipv4.ip

        server_type_name: str | None = server.server_type.name if server.server_type else None
        location_name: str | None = server.datacenter.location.name if server.datacenter else None
        protection = server.protection if isinstance(server.protection, dict) else {}
        is_protected: bool = bool(protection.get("delete", False))

        result.append(
            VirtualMachineOut(
                name=server.name,
                status=status,
                server_id=server.id,
                public_ip=public_ip,
                server_type=server_type_name,
                location=location_name,
                protected=is_protected,
                can_restore=False,
                can_archive=not is_protected,
                can_start=(status == "stopped") and not is_protected,
                can_stop=(status == "running") and not is_protected,
            )
        )
    return result


async def list_snapshots_by_label() -> list[SnapshotOut]:
    """Return all Hetzner snapshots that have a 'vm-name' label."""
    try:
        client = _get_client()
        images: list[Any] = await asyncio.to_thread(
            client.images.get_all, type="snapshot", label_selector="vm-name"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to reach Hetzner Cloud. Please try again.",
        ) from exc

    return [
        SnapshotOut(
            id=img.id,
            description=img.description or "",
            created_at=str(img.created) if img.created else "",
            vm_name=img.labels.get("vm-name", ""),
            server_type=img.labels.get("server-type"),
            location=img.labels.get("location"),
        )
        for img in images
    ]


# --------------------------------------------------------------------------- #
# US2 — Power on/off
# --------------------------------------------------------------------------- #


async def power_on(name: str) -> None:
    """Power on a stopped server by name."""
    try:
        client = _get_client()
        servers: list[Any] = await asyncio.to_thread(client.servers.get_all, name=name)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to reach Hetzner Cloud. Please try again.",
        ) from exc

    if not servers:
        raise HTTPException(
            status_code=404,
            detail=f"VM '{name}' not found or is not in the correct state.",
        )
    try:
        await asyncio.to_thread(client.servers.power_on, servers[0])
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to reach Hetzner Cloud. Please try again.",
        ) from exc


async def power_off(name: str) -> None:
    """Gracefully power off a running server by name."""
    try:
        client = _get_client()
        servers: list[Any] = await asyncio.to_thread(client.servers.get_all, name=name)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to reach Hetzner Cloud. Please try again.",
        ) from exc

    if not servers:
        raise HTTPException(
            status_code=404,
            detail=f"VM '{name}' not found or is not in the correct state.",
        )
    try:
        await asyncio.to_thread(client.servers.shutdown, servers[0])
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to reach Hetzner Cloud. Please try again.",
        ) from exc


# --------------------------------------------------------------------------- #
# US3 — Archive (shutdown + create snapshot + delete server)
# --------------------------------------------------------------------------- #


async def shutdown_server(name: str) -> None:
    """Hard power off a server and wait until fully stopped."""
    try:
        client = _get_client()
        servers: list[Any] = await asyncio.to_thread(client.servers.get_all, name=name)
        if not servers:
            raise HTTPException(status_code=404, detail=f"VM '{name}' not found.")
        action = await asyncio.to_thread(servers[0].power_off)
        if action:
            await _poll_action(client, action)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to reach Hetzner Cloud. Please try again.",
        ) from exc


async def create_snapshot(name: str, server_id: int) -> int:
    """Create a labeled snapshot for the server, wait for completion, return image ID."""
    try:
        client = _get_client()
        servers: list[Any] = await asyncio.to_thread(client.servers.get_all, name=name)
        if not servers:
            raise HTTPException(status_code=404, detail=f"VM '{name}' not found.")
        server = servers[0]
        server_type_name = server.server_type.name if server.server_type else "cx22"
        location_name = server.datacenter.location.name if server.datacenter else "nbg1"
        response = await asyncio.to_thread(
            lambda: client.servers.create_image(
                server,
                type="snapshot",
                description=name,
                labels={"vm-name": name, "server-type": server_type_name, "location": location_name},
            )
        )
        # Poll until the snapshot action completes (no timeout — large VMs can take many minutes)
        action = response.action
        if action:
            await _poll_action(client, action)
        image = response.image
        if image is None:
            raise HTTPException(
                status_code=500,
                detail="Snapshot creation did not return an image.",
            )
        return int(image.id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to reach Hetzner Cloud. Please try again.",
        ) from exc


async def delete_server_by_name(name: str) -> None:
    """Delete a live server by name without creating a snapshot."""
    try:
        client = _get_client()
        servers: list[Any] = await asyncio.to_thread(client.servers.get_all, name=name)
        if not servers:
            raise HTTPException(status_code=404, detail=f"VM '{name}' not found.")
        action = await asyncio.to_thread(servers[0].delete)
        if action:
            await _poll_action(client, action)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to reach Hetzner Cloud. Please try again.",
        ) from exc


async def delete_server(server_id: int) -> None:
    """Delete a server by ID."""
    try:
        client = _get_client()
        server = await asyncio.to_thread(client.servers.get_by_id, server_id)
        if server is None:
            raise HTTPException(status_code=404, detail=f"Server ID {server_id} not found.")
        action = await asyncio.to_thread(server.delete)
        if action:
            await _poll_action(client, action)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to reach Hetzner Cloud. Please try again.",
        ) from exc


# --------------------------------------------------------------------------- #
# US4 — Restore (create server from snapshot)
# --------------------------------------------------------------------------- #


async def _try_create_server(
    client: Client,
    name: str,
    snapshot_id: int,
    server_type: str,
    location: str,
    ssh_key_name: str | None,
) -> dict:
    """Attempt a single (server_type, location) combination; raises on failure."""
    from hcloud.locations import Location
    from hcloud.server_types import ServerType
    from hcloud.ssh_keys import SSHKey

    response = await asyncio.to_thread(
        client.servers.create,
        name=name,
        server_type=ServerType(name=server_type),
        image=Image(id=snapshot_id),
        location=Location(name=location),
        ssh_keys=[SSHKey(name=ssh_key_name)] if ssh_key_name else [],
    )
    server = response.server
    # Poll until IP is assigned
    for _ in range(20):
        refreshed = await asyncio.to_thread(client.servers.get_by_id, server.id)
        if refreshed and refreshed.public_net.ipv4 and refreshed.public_net.ipv4.ip:
            return {"server_id": refreshed.id, "public_ip": refreshed.public_net.ipv4.ip}
        await asyncio.sleep(2)
    raise HTTPException(
        status_code=500,
        detail="Server was created but IP was not assigned in time.",
    )


async def create_server_from_snapshot(
    name: str,
    snapshot_id: int,
    preferred_type: str = "cx23",
    preferred_location: str = "nbg1",
    ssh_key_name: str | None = None,
) -> dict:
    """Create a new server from a snapshot image with type/location fallback.

    Tries preferred_type in preferred_location first. Falls back through other
    locations, then through upgrade server types. Returns dict with keys:
    server_id, public_ip, actual_type, actual_location, upgraded.
    """
    client = _get_client()
    fallback_locs = [preferred_location] + [
        loc for loc in _FALLBACK_LOCATIONS if loc != preferred_location
    ]
    type_candidates = [preferred_type] + _UPGRADE_PATHS.get(preferred_type, [])

    log.info(
        "[hetzner] restore %s: preferred_type=%s preferred_location=%s "
        "type_candidates=%s fallback_locs=%s",
        name, preferred_type, preferred_location, type_candidates, fallback_locs,
    )

    last_exc: Exception | None = None
    for candidate_type in type_candidates:
        for loc in fallback_locs:
            log.info("[hetzner] restore %s: trying type=%s loc=%s", name, candidate_type, loc)
            try:
                result = await _try_create_server(
                    client, name, snapshot_id, candidate_type, loc, ssh_key_name
                )
                result["upgraded"] = candidate_type != preferred_type
                result["actual_type"] = candidate_type
                result["actual_location"] = loc
                log.info("[hetzner] restore %s: success type=%s loc=%s", name, candidate_type, loc)
                return result
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "[hetzner] restore %s: type=%s loc=%s failed: %s: %s",
                    name, candidate_type, loc, type(exc).__name__, exc,
                )
                last_exc = exc
                continue

    raise HTTPException(
        status_code=500,
        detail=f"Could not restore VM in any available type or location. Last error: {last_exc}",
    )


# --------------------------------------------------------------------------- #
# US4/US5 — Firewall upsert (shared)
# --------------------------------------------------------------------------- #


async def upsert_ip_rule(firewall_name: str, ip: str) -> bool:
    """Add ip/32 to a firewall's inbound rules if not already present.

    Returns True if the IP was already present (idempotent — no API call made).
    Returns False if a new rule was added.
    Raises HTTPException(404) if the firewall is not found.
    """
    try:
        client = _get_client()
        firewalls: list[Any] = await asyncio.to_thread(
            client.firewalls.get_all, name=firewall_name
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to reach Hetzner Cloud. Please try again.",
        ) from exc

    if not firewalls:
        raise HTTPException(
            status_code=404,
            detail=f"Firewall '{firewall_name}' not found.",
        )
    firewall = firewalls[0]

    # Check if rule already exists
    target_cidr = f"{ip}/32"
    for rule in firewall.rules:
        if hasattr(rule, "source_ips") and target_cidr in (rule.source_ips or []):
            return True

    # Add new inbound allow rule
    from hcloud.firewalls.domain import FirewallRule

    new_rules = list(firewall.rules) + [
        FirewallRule(
            direction="in",
            protocol="tcp",
            port="any",
            source_ips=[target_cidr],
        ),
        FirewallRule(
            direction="in",
            protocol="udp",
            port="any",
            source_ips=[target_cidr],
        ),
    ]
    try:
        await asyncio.to_thread(client.firewalls.set_rules, firewall, new_rules)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to reach Hetzner Cloud. Please try again.",
        ) from exc

    return False
