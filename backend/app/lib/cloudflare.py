"""Cloudflare DNS API client — update_a_record()."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
from fastapi import HTTPException

from app.settings import settings
from app.models.db import VmConfig


async def update_a_record(vm_name: str, new_ip: str, db: AsyncSession, zone_id: str = "", cloudflare_api_token: str = "") -> None:
    """Update the Cloudflare A record for the VM's domain to new_ip.

    Looks up the VM's domain from VmConfig, derives the zone root (last two labels),
    then calls Cloudflare REST API v4 to PATCH the record.

    Raises HTTPException(502) on any Cloudflare API failure.
    """
    # Resolve domain from VmConfig
    result = await db.execute(select(VmConfig).where(VmConfig.vm_name == vm_name))
    vm_config = result.scalar_one_or_none()

    if vm_config is None or not vm_config.domain:
        raise HTTPException(
            status_code=502,
            detail=f"No domain configured for VM '{vm_name}'. Cannot update DNS.",
        )

    domain = vm_config.domain
    # Use explicit zone name if configured; otherwise derive from last two domain labels
    if settings.CLOUDFLARE_ZONE_NAME:
        zone_root = settings.CLOUDFLARE_ZONE_NAME
    else:
        parts = domain.split(".")
        zone_root = ".".join(parts[-2:]) if len(parts) >= 2 else domain

    headers = {
        "Authorization": f"Bearer {cloudflare_api_token or settings.CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(base_url="https://api.cloudflare.com") as client:
            # 1. Resolve zone ID
            if zone_id:
                resolved_zone_id = zone_id
            elif settings.CLOUDFLARE_ZONE_ID:
                resolved_zone_id = settings.CLOUDFLARE_ZONE_ID
            else:
                zones_resp = await client.get(
                    "/client/v4/zones", params={"name": zone_root}, headers=headers
                )
                zones_data = zones_resp.json()
                cf_errors = zones_data.get("errors", [])
                if not zones_data.get("success") or not zones_data.get("result"):
                    err_detail = "; ".join(e.get("message", str(e)) for e in cf_errors)
                    raise HTTPException(
                        status_code=502,
                        detail=(
                            f"Cloudflare zone '{zone_root}' not found. "
                            f"Set CLOUDFLARE_ZONE_ID in .env to bypass this lookup. "
                            + (f"API errors: {err_detail}" if err_detail else "Check CLOUDFLARE_API_TOKEN and zone name.")
                        ),
                    )
                resolved_zone_id = zones_data["result"][0]["id"]

            # 2. Look up existing A record
            records_resp = await client.get(
                f"/client/v4/zones/{resolved_zone_id}/dns_records",
                params={"type": "A", "name": domain},
                headers=headers,
            )
            records_data = records_resp.json()
            existing = records_data.get("result") or []

            if existing:
                # 3a. PATCH the existing record
                record_id = existing[0]["id"]
                write_resp = await client.patch(
                    f"/client/v4/zones/{resolved_zone_id}/dns_records/{record_id}",
                    json={"content": new_ip},
                    headers=headers,
                )
            else:
                # 3b. CREATE the record (proxied=False so the real IP is exposed)
                write_resp = await client.post(
                    f"/client/v4/zones/{resolved_zone_id}/dns_records",
                    json={"type": "A", "name": domain, "content": new_ip, "ttl": 1, "proxied": False},
                    headers=headers,
                )
            write_data = write_resp.json()
            if not write_data.get("success"):
                errors = write_data.get("errors", [])
                raise HTTPException(
                    status_code=502,
                    detail=f"Cloudflare DNS write failed: {errors}",
                )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Unable to reach Cloudflare API. Please try again.",
        ) from exc


async def delete_dns_record(vm_name: str, db: AsyncSession, zone_id: str = "", cloudflare_api_token: str = "") -> None:
    """Delete the Cloudflare A record for the VM's domain.

    No-op (with a log) if no domain is configured or the record doesn't exist.
    Raises HTTPException(502) on API auth/network failures.
    """
    result = await db.execute(select(VmConfig).where(VmConfig.vm_name == vm_name))
    vm_config = result.scalar_one_or_none()

    if vm_config is None or not vm_config.domain:
        return  # nothing to remove

    domain = vm_config.domain
    if settings.CLOUDFLARE_ZONE_NAME:
        zone_root = settings.CLOUDFLARE_ZONE_NAME
    else:
        parts = domain.split(".")
        zone_root = ".".join(parts[-2:]) if len(parts) >= 2 else domain

    headers = {
        "Authorization": f"Bearer {cloudflare_api_token or settings.CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(base_url="https://api.cloudflare.com") as client:
            if zone_id:
                resolved_zone_id = zone_id
            elif settings.CLOUDFLARE_ZONE_ID:
                resolved_zone_id = settings.CLOUDFLARE_ZONE_ID
            else:
                zones_resp = await client.get(
                    "/client/v4/zones", params={"name": zone_root}, headers=headers
                )
                zones_data = zones_resp.json()
                if not zones_data.get("success") or not zones_data.get("result"):
                    raise HTTPException(status_code=502, detail=f"Cloudflare zone '{zone_root}' not found.")
                resolved_zone_id = zones_data["result"][0]["id"]

            records_resp = await client.get(
                f"/client/v4/zones/{resolved_zone_id}/dns_records",
                params={"type": "A", "name": domain},
                headers=headers,
            )
            records_data = records_resp.json()
            existing = records_data.get("result") or []
            if not existing:
                return  # record doesn't exist — nothing to delete

            record_id = existing[0]["id"]
            del_resp = await client.delete(
                f"/client/v4/zones/{resolved_zone_id}/dns_records/{record_id}",
                headers=headers,
            )
            del_data = del_resp.json()
            if not del_data.get("success"):
                errors = del_data.get("errors", [])
                raise HTTPException(status_code=502, detail=f"Cloudflare DNS delete failed: {errors}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Unable to reach Cloudflare API. Please try again.",
        ) from exc
