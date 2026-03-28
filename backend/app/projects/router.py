from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import get_current_user
from app.database import get_db
from app.models.db import HetznerProject, User, UserProjectPermission

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
async def list_accessible_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return all projects accessible to the current user.

    Superadmins see all active projects. Regular users see only those they
    have an explicit permission record for.
    """
    if current_user.is_superadmin:
        result = await db.execute(
            select(HetznerProject)
            .where(HetznerProject.is_active == True)  # noqa: E712
            .order_by(HetznerProject.id)
        )
        projects = result.scalars().all()
    else:
        result = await db.execute(
            select(HetznerProject)
            .join(
                UserProjectPermission,
                UserProjectPermission.project_id == HetznerProject.id,
            )
            .where(
                UserProjectPermission.user_id == current_user.id,
                HetznerProject.is_active == True,  # noqa: E712
            )
            .order_by(HetznerProject.id)
        )
        projects = result.scalars().all()

    return JSONResponse(
        {
            "projects": [
                {
                    "id": p.id,
                    "name": p.name,
                    "firewall_name": p.firewall_name,
                    "is_active": p.is_active,
                }
                for p in projects
            ]
        }
    )
