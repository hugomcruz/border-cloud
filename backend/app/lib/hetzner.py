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


def _get_client(token: str | None = None) -> Client:
    """Return a configured hcloud Client. Token falls back to settings for legacy use."""
    return Client(token=token or settings.HETZNER_API_TOKEN)


async def _poll_action(client: Client, action: Any, poll_interval: float = 10.0, max_retries: int = 5) -> None:
    """Async-friendly replacement for action.wait_until_finished.

    Polls the action status every `poll_interval` seconds using asyncio.sleep
    so the event loop is never blocked.  No hardcoded timeout — keeps polling
    until Hetzner reports success or error (important for slow operations like
    Windows VM snapshots).  Retries up to `max_retries` times on transient
    Hetzner API errors (e.g. internal_server_error) before giving up.
    """
    from hcloud._exceptions import APIException  # noqa: PLC0415

    consecutive_errors = 0
    while True:
        try:
            fresh = await asyncio.to_thread(client.actions.get_by_id, action.id)
            consecutive_errors = 0  # reset on success
        except APIException as exc:
            consecutive_errors += 1
            log.warning(
                "[hetzner] transient error polling action %s (%d/%d): %s",
                action.id, consecutive_errors, max_retries, exc,
            )
            if consecutive_errors >= max_retries:
                raise HTTPException(
                    status_code=502,
                    detail="Unable to reach Hetzner Cloud. Please try again.",
                ) from exc
            await asyncio.sleep(poll_interval)
            continue

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


async def list_servers(token: str) -> list[VirtualMachineOut]:
    """Return all live Hetzner servers mapped to VirtualMachineOut."""
    try:
        client = _get_client(token)
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


async def list_snapshots_by_label(token: str) -> list[SnapshotOut]:
    """Return all Hetzner snapshots that have a 'vm-name' label."""
    try:
        client = _get_client(token)
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


async def power_on(name: str, token: str) -> None:
    """Power on a stopped server by name."""
    try:
        client = _get_client(token)
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


async def power_off(name: str, token: str) -> None:
    """Gracefully power off a running server by name."""
    try:
        client = _get_client(token)
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


async def shutdown_server(name: str, token: str) -> None:
    """Hard power off a server and wait until fully stopped."""
    try:
        client = _get_client(token)
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


async def create_snapshot(name: str, server_id: int, token: str) -> int:
    """Create a labeled snapshot for the server, wait for completion, return image ID."""
    from datetime import datetime, timezone  # noqa: PLC0415

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    snapshot_description = f"{name}-{timestamp}"
    try:
        client = _get_client(token)
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
                description=snapshot_description,
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


async def delete_server_by_name(name: str, token: str) -> None:
    """Delete a live server by name without creating a snapshot."""
    try:
        client = _get_client(token)
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


async def delete_server(server_id: int, token: str) -> None:
    """Delete a server by ID."""
    try:
        client = _get_client(token)
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


async def prune_old_snapshots(name: str, token: str, keep: int = 3) -> list[int]:
    """Delete old snapshots for a VM, keeping only the `keep` most recent ones.

    Returns a list of image IDs that were deleted.
    """
    try:
        client = _get_client(token)
        images: list[Any] = await asyncio.to_thread(
            client.images.get_all, type="snapshot", label_selector=f"vm-name={name}"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to reach Hetzner Cloud. Please try again.",
        ) from exc

    # Sort newest first
    sorted_images = sorted(images, key=lambda img: img.created or "", reverse=True)
    to_delete = sorted_images[keep:]
    deleted_ids: list[int] = []
    for img in to_delete:
        try:
            await asyncio.to_thread(img.delete)
            deleted_ids.append(img.id)
        except Exception:  # noqa: BLE001
            pass  # best-effort; don't abort the archive if pruning fails
    return deleted_ids


async def delete_all_snapshots(name: str, token: str) -> list[int]:
    """Delete all snapshots for a VM.

    Returns a list of deleted image IDs.
    """
    try:
        client = _get_client(token)
        images: list[Any] = await asyncio.to_thread(
            client.images.get_all, type="snapshot", label_selector=f"vm-name={name}"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to reach Hetzner Cloud. Please try again.",
        ) from exc

    deleted_ids: list[int] = []
    for img in images:
        try:
            await asyncio.to_thread(img.delete)
            deleted_ids.append(img.id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete snapshot {img.id}: {exc}",
            ) from exc
    return deleted_ids


# --------------------------------------------------------------------------- #
# US4 — Restore (create server from snapshot)
# --------------------------------------------------------------------------- #


async def get_server_attachment_config(server_id: int, token: str) -> dict:
    """Return firewall IDs, private network IDs, and IP version flags for a server.

    Returns:
      {
        "firewalls": [int, ...],
        "networks": [int, ...],
        "enable_ipv4": bool,
        "enable_ipv6": bool,
      }
    """
    try:
        client = _get_client(token)
        server = await asyncio.to_thread(client.servers.get_by_id, server_id)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to reach Hetzner Cloud. Please try again.",
        ) from exc

    if server is None:
        return {"firewalls": [], "networks": [], "enable_ipv4": True, "enable_ipv6": True}

    # Firewalls are at server.public_net.firewalls (list of PublicNetworkFirewall)
    public_net = getattr(server, "public_net", None)
    fw_list = getattr(public_net, "firewalls", None) or []
    firewall_ids: list[int] = [
        fw_entry.firewall.id
        for fw_entry in fw_list
        if getattr(fw_entry, "firewall", None) is not None
    ]

    # Private networks are at server.private_net (list of PrivateNet)
    network_ids: list[int] = [
        pn.network.id
        for pn in (server.private_net or [])
        if getattr(pn, "network", None) is not None
    ]

    # IPv4/IPv6 presence is indicated by whether the address object is non-None
    enable_ipv4: bool = getattr(public_net, "ipv4", None) is not None
    enable_ipv6: bool = getattr(public_net, "ipv6", None) is not None

    return {
        "firewalls": firewall_ids,
        "networks": network_ids,
        "enable_ipv4": enable_ipv4,
        "enable_ipv6": enable_ipv6,
    }


async def _try_create_server(
    client: Client,
    name: str,
    snapshot_id: int,
    server_type: str,
    location: str,
    ssh_key_name: str | None,
    firewall_ids: list[int] | None = None,
    network_ids: list[int] | None = None,
    enable_ipv4: bool = True,
    enable_ipv6: bool = True,
) -> dict:
    """Attempt a single (server_type, location) combination; raises on failure."""
    from hcloud.firewalls.domain import Firewall as FirewallRef
    from hcloud.locations import Location
    from hcloud.networks.domain import Network as NetworkRef
    from hcloud.server_types import ServerType
    from hcloud.servers.domain import ServerCreatePublicNetwork
    from hcloud.ssh_keys import SSHKey

    fw_objects = [FirewallRef(id=fid) for fid in (firewall_ids or [])]
    net_objects = [NetworkRef(id=nid) for nid in (network_ids or [])]

    response = await asyncio.to_thread(
        client.servers.create,
        name=name,
        server_type=ServerType(name=server_type),
        image=Image(id=snapshot_id),
        location=Location(name=location),
        ssh_keys=[SSHKey(name=ssh_key_name)] if ssh_key_name else [],
        user_data="#cloud-config\nssh_deletekeys: false\n",
        firewalls=fw_objects if fw_objects else None,
        networks=net_objects if net_objects else None,
        public_net=ServerCreatePublicNetwork(enable_ipv4=enable_ipv4, enable_ipv6=enable_ipv6),
    )
    server = response.server
    # Poll until IP is assigned (or IPv4 is disabled)
    for _ in range(20):
        refreshed = await asyncio.to_thread(client.servers.get_by_id, server.id)
        if refreshed:
            if not enable_ipv4:
                # IPv4 disabled — return server_id with no public IP
                return {"server_id": refreshed.id, "public_ip": None}
            if refreshed.public_net.ipv4 and refreshed.public_net.ipv4.ip:
                return {"server_id": refreshed.id, "public_ip": refreshed.public_net.ipv4.ip}
        await asyncio.sleep(2)
    raise HTTPException(
        status_code=500,
        detail="Server was created but IP was not assigned in time.",
    )


async def create_server_from_snapshot(
    name: str,
    snapshot_id: int,
    token: str,
    preferred_type: str = "cx23",
    preferred_location: str = "nbg1",
    ssh_key_name: str | None = None,
    firewall_ids: list[int] | None = None,
    network_ids: list[int] | None = None,
    enable_ipv4: bool = True,
    enable_ipv6: bool = True,
) -> dict:
    """Create a new server from a snapshot image with type/location fallback.

    Tries preferred_type in preferred_location first. Falls back through other
    locations, then through upgrade server types. Returns dict with keys:
    server_id, public_ip, actual_type, actual_location, upgraded.
    """
    client = _get_client(token)
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
                    client, name, snapshot_id, candidate_type, loc, ssh_key_name,
                    firewall_ids, network_ids, enable_ipv4, enable_ipv6,
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


async def upsert_user_ip_rule(firewall_name: str, ip: str, token: str, username: str) -> None:
    """Set (or replace) a firewall rule for a specific user identified by `username`.

    Removes any existing rules whose `description` matches `username`, then adds
    fresh TCP + UDP inbound allow rules tagged with that description.
    This keeps one IP per user in the firewall and allows updating when the IP changes.
    """
    try:
        client = _get_client(token)
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

    from hcloud.firewalls.domain import FirewallRule

    target_cidr = f"{ip}/32"

    # Filter out any existing rules belonging to this user
    kept_rules = [
        rule for rule in firewall.rules
        if getattr(rule, "description", None) != username
    ]

    # Check if the user's rule is already present with the correct IP
    existing_ips = {
        ip_cidr
        for rule in firewall.rules
        if getattr(rule, "description", None) == username
        for ip_cidr in (rule.source_ips or [])
    }
    if existing_ips == {target_cidr}:
        # Already up-to-date — no API call needed
        return

    new_rules = kept_rules + [
        FirewallRule(
            direction="in",
            protocol="tcp",
            port="any",
            source_ips=[target_cidr],
            description=username,
        ),
        FirewallRule(
            direction="in",
            protocol="udp",
            port="any",
            source_ips=[target_cidr],
            description=username,
        ),
    ]
    try:
        await asyncio.to_thread(client.firewalls.set_rules, firewall, new_rules)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to reach Hetzner Cloud. Please try again.",
        ) from exc


async def remove_ip_rule_by_description(firewall_name: str, token: str, description: str) -> bool:
    """Remove all firewall rules whose `description` matches the given value.

    Returns True if any rules were removed, False if none matched.
    Raises HTTPException(404) if the firewall is not found.
    """
    try:
        client = _get_client(token)
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

    kept = [r for r in firewall.rules if getattr(r, "description", None) != description]
    if len(kept) == len(firewall.rules):
        return False  # nothing to remove

    try:
        await asyncio.to_thread(client.firewalls.set_rules, firewall, kept)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to reach Hetzner Cloud. Please try again.",
        ) from exc

    return True


# --------------------------------------------------------------------------- #
# Provision — create a brand-new server from a public OS image
# --------------------------------------------------------------------------- #

# Preferred datacenter order (fsn1 = Falkenstein, nbg1 = Nuremberg, hel1 = Helsinki)
_PROVISION_LOCATIONS = ["fsn1", "nbg1", "hel1"]

# Canonical Hetzner image names for supported OS options
_OS_IMAGE_NAMES: dict[str, str] = {
    "debian-13": "debian-13",
    "centos-stream-10": "centos-stream-10",
    "rocky-linux-10": "rocky-10",
}

_K3S_CLOUD_CONFIG_TEMPLATE = """\
#cloud-config
packages:
  - curl
users:
  - name: border
    ssh-authorized-keys:
      - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJg2/bQ63duykspuNeOHBMr2rpqOnMtByYCM6QdUwqOP hcruz@Hugos-MacBook-Pro.local
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
runcmd:
  - apt-get update -y
  - hostnamectl set-hostname {fqdn}
  - curl https://get.k3s.io | INSTALL_K3S_EXEC="--disable traefik --disable-cloud-controller" sh -
  - chown border:border /etc/rancher/k3s/k3s.yaml
  - chown border:border /var/lib/rancher/k3s/server/node-token
"""


async def get_project_resources(token: str) -> dict:
    """Return all SSH keys, private networks, and firewalls available in a project."""
    try:
        client = _get_client(token)
        ssh_keys: list[Any] = await asyncio.to_thread(client.ssh_keys.get_all)
        networks: list[Any] = await asyncio.to_thread(client.networks.get_all)
        firewalls: list[Any] = await asyncio.to_thread(client.firewalls.get_all)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to reach Hetzner Cloud. Please try again.",
        ) from exc

    return {
        "ssh_keys": [{"id": k.id, "name": k.name} for k in ssh_keys],
        "networks": [{"id": n.id, "name": n.name} for n in networks],
        "firewalls": [{"id": f.id, "name": f.name} for f in firewalls],
    }


async def provision_server(
    name: str,
    server_type: str,
    os_image: str,
    token: str,
    user_data: str | None = None,
    ssh_key_names: list[str] | None = None,
    firewall_ids: list[int] | None = None,
    network_ids: list[int] | None = None,
) -> dict:
    """Create a brand-new server from a public OS image.

    Tries datacenters in order: Falkenstein → Nuremberg → Helsinki.
    IPv4 enabled, IPv6 disabled.
    Returns {server_id, public_ip, actual_location}.
    """
    from hcloud.firewalls.domain import Firewall as FirewallRef
    from hcloud.images.domain import Image as ImageRef
    from hcloud.locations import Location
    from hcloud.networks.domain import Network as NetworkRef
    from hcloud.server_types import ServerType
    from hcloud.servers.domain import ServerCreatePublicNetwork
    from hcloud.ssh_keys import SSHKey

    image_name = _OS_IMAGE_NAMES.get(os_image, os_image)
    client = _get_client(token)

    fw_objects = [FirewallRef(id=fid) for fid in (firewall_ids or [])]
    net_objects = [NetworkRef(id=nid) for nid in (network_ids or [])]
    ssh_key_objects = [SSHKey(name=k) for k in (ssh_key_names or [])]

    last_exc: Exception | None = None
    for loc in _PROVISION_LOCATIONS:
        log.info("[hetzner] provision %s: trying type=%s image=%s loc=%s", name, server_type, image_name, loc)
        try:
            response = await asyncio.to_thread(
                client.servers.create,
                name=name,
                server_type=ServerType(name=server_type),
                image=ImageRef(name=image_name),
                location=Location(name=loc),
                ssh_keys=ssh_key_objects if ssh_key_objects else [],
                user_data=user_data or "",
                firewalls=fw_objects if fw_objects else None,
                networks=net_objects if net_objects else None,
                public_net=ServerCreatePublicNetwork(enable_ipv4=True, enable_ipv6=False),
            )
            server = response.server
            # Poll until public IPv4 is assigned
            for _ in range(20):
                refreshed = await asyncio.to_thread(client.servers.get_by_id, server.id)
                if refreshed and refreshed.public_net.ipv4 and refreshed.public_net.ipv4.ip:
                    log.info("[hetzner] provision %s: success loc=%s ip=%s", name, loc, refreshed.public_net.ipv4.ip)
                    return {"server_id": refreshed.id, "public_ip": refreshed.public_net.ipv4.ip, "actual_location": loc}
                await asyncio.sleep(2)
            raise HTTPException(status_code=500, detail="Server created but IP not assigned in time.")
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("[hetzner] provision %s: loc=%s failed: %s", name, loc, exc)
            last_exc = exc
            continue

    raise HTTPException(
        status_code=500,
        detail=f"Could not provision server in any datacenter. Last error: {last_exc}",
    )
