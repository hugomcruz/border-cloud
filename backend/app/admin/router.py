import logging

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import get_current_user, require_superadmin
from app.database import get_db
from app.models.db import HetznerProject, OperationLog, User, UserProjectPermission
from app.admin.schemas import (
    PermissionOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin"])
log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #

@router.get("/users", response_model=list[UserOut])
async def list_users(
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    result = await db.execute(select(User).order_by(User.id))
    return list(result.scalars().all())


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> User:
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Username already exists")

    password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt(rounds=12)).decode()
    user = User(
        username=body.username,
        password_hash=password_hash,
        is_superadmin=body.is_superadmin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    log.info("Created user '%s' (superadmin=%s)", user.username, user.is_superadmin)
    return user


@router.put("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdate,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if body.password is not None:
        user.password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt(rounds=12)).decode()
    if body.is_superadmin is not None:
        # Prevent superadmin from removing their own superadmin status
        if user.id == current_user.id and not body.is_superadmin:
            raise HTTPException(status_code=400, detail="Cannot remove your own superadmin status")
        user.is_superadmin = body.is_superadmin
    if body.is_active is not None:
        user.is_active = body.is_active

    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> None:
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()


# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #

@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> list[HetznerProject]:
    result = await db.execute(select(HetznerProject).order_by(HetznerProject.id))
    return list(result.scalars().all())


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> HetznerProject:
    existing = await db.execute(select(HetznerProject).where(HetznerProject.name == body.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Project name already exists")

    project = HetznerProject(
        name=body.name,
        api_token=body.api_token,
        firewall_name=body.firewall_name,
        firewall_internal=body.firewall_internal,
        cloudflare_zone_id=body.cloudflare_zone_id,
        cloudflare_api_token=body.cloudflare_api_token,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    log.info("Created Hetzner project '%s'", project.name)
    return project


@router.put("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: int,
    body: ProjectUpdate,
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> HetznerProject:
    project = await db.get(HetznerProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if body.name is not None:
        project.name = body.name
    if body.api_token is not None:
        project.api_token = body.api_token
    if body.firewall_name is not None:
        project.firewall_name = body.firewall_name
    if body.firewall_internal is not None:
        project.firewall_internal = body.firewall_internal
    if body.cloudflare_zone_id is not None:
        project.cloudflare_zone_id = body.cloudflare_zone_id
    if body.cloudflare_api_token is not None:
        project.cloudflare_api_token = body.cloudflare_api_token
    if body.is_active is not None:
        project.is_active = body.is_active

    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int,
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> None:
    project = await db.get(HetznerProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(project)
    await db.commit()


# --------------------------------------------------------------------------- #
# Project ↔ User permissions
# --------------------------------------------------------------------------- #

@router.get("/projects/{project_id}/users", response_model=list[PermissionOut])
async def list_project_users(
    project_id: int,
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    result = await db.execute(
        select(UserProjectPermission, User.username)
        .join(User, User.id == UserProjectPermission.user_id)
        .where(UserProjectPermission.project_id == project_id)
    )
    rows = result.all()
    return [
        {"user_id": perm.user_id, "project_id": perm.project_id, "username": username}
        for perm, username in rows
    ]


@router.post(
    "/projects/{project_id}/users/{user_id}",
    response_model=PermissionOut,
    status_code=status.HTTP_201_CREATED,
)
async def grant_project_access(
    project_id: int,
    user_id: int,
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project = await db.get(HetznerProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    existing = await db.execute(
        select(UserProjectPermission).where(
            UserProjectPermission.user_id == user_id,
            UserProjectPermission.project_id == project_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Permission already exists")

    perm = UserProjectPermission(user_id=user_id, project_id=project_id)
    db.add(perm)
    await db.commit()
    return {"user_id": user_id, "project_id": project_id, "username": user.username}


@router.delete(
    "/projects/{project_id}/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_project_access(
    project_id: int,
    user_id: int,
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(UserProjectPermission).where(
            UserProjectPermission.user_id == user_id,
            UserProjectPermission.project_id == project_id,
        )
    )
    perm = result.scalar_one_or_none()
    if perm is None:
        raise HTTPException(status_code=404, detail="Permission not found")
    await db.delete(perm)
    await db.commit()


# --------------------------------------------------------------------------- #
# VM operation logs (admin view — all VMs)
# --------------------------------------------------------------------------- #

@router.get("/vms/logs")
async def list_vm_logs(
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    vm_name: str = Query(""),
    operation: str = Query(""),
    status_filter: str = Query("", alias="status"),
) -> dict:
    """Return operation logs for all VMs (superadmin only)."""
    stmt = select(OperationLog).order_by(OperationLog.started_at.desc()).limit(limit)
    if vm_name:
        stmt = stmt.where(OperationLog.vm_name.ilike(f"%{vm_name}%"))
    if operation:
        stmt = stmt.where(OperationLog.operation == operation)
    if status_filter:
        stmt = stmt.where(OperationLog.status == status_filter)

    result = await db.execute(stmt)
    logs = result.scalars().all()
    return {
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
    }

