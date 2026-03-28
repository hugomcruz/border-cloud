import ipaddress

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import get_current_user
from app.database import get_db
from app.lib.hetzner import upsert_user_ip_rule
from app.models.db import HetznerProject, User, UserProjectPermission

router = APIRouter(prefix="/firewall", tags=["firewall"])


class FirewallSyncRequest(BaseModel):
    ip: str
    project_id: int


@router.post("/sync")
async def sync_firewall(
    body: FirewallSyncRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Add the given IP to the Hetzner firewall's allowed source IPs.

    Validates the IP is a valid IPv4 address. Uses the project's token and firewall name.
    Returns {ip, alreadyPresent}.
    """
    # Validate IPv4
    try:
        ipaddress.ip_address(body.ip)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid IP address: {body.ip}") from exc

    # Resolve project and permission
    if not current_user.is_superadmin:
        perm = await db.execute(
            select(UserProjectPermission).where(
                UserProjectPermission.user_id == current_user.id,
                UserProjectPermission.project_id == body.project_id,
            )
        )
        if perm.scalar_one_or_none() is None:
            raise HTTPException(status_code=403, detail="No access to this project")

    result = await db.execute(
        select(HetznerProject).where(
            HetznerProject.id == body.project_id,
            HetznerProject.is_active.is_(True),
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    firewall_name = project.firewall_name
    if not firewall_name:
        raise HTTPException(
            status_code=422,
            detail="Firewall name not configured for this project.",
        )

    await upsert_user_ip_rule(firewall_name, body.ip, project.api_token, current_user.username)
    return JSONResponse({"ip": body.ip, "alreadyPresent": False})
