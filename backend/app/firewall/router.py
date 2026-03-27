import ipaddress

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import get_current_user
from app.database import get_db
from app.lib.hetzner import upsert_ip_rule
from app.models.db import AppConfig, User

router = APIRouter(prefix="/firewall", tags=["firewall"])


class FirewallSyncRequest(BaseModel):
    ip: str


@router.post("/sync")
async def sync_firewall(
    body: FirewallSyncRequest,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Add the given IP to the Hetzner firewall's allowed source IPs.

    Validates the IP is a valid IPv4 address. Reads the firewall name from AppConfig.
    Returns {ip, alreadyPresent}.
    """
    # Validate IPv4
    try:
        ipaddress.ip_address(body.ip)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid IP address: {body.ip}") from exc

    # Get firewall name from AppConfig
    result = await db.execute(select(AppConfig).where(AppConfig.key == "hetzner_firewall_name"))
    config = result.scalar_one_or_none()
    firewall_name = config.value if config else ""

    if not firewall_name:
        raise HTTPException(
            status_code=422,
            detail="Firewall name not configured. Set HETZNER_FIREWALL_NAME env var or hetzner_firewall_name in AppConfig.",
        )

    already_present = await upsert_ip_rule(firewall_name, body.ip)
    return JSONResponse({"ip": body.ip, "alreadyPresent": already_present})
