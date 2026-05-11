from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.service import get_current_user
from app.config.schemas import (
    AppConfigOut,
    AppConfigUpdate,
    VmConfigCreate,
    VmConfigOut,
    VmConfigUpdate,
    VmFirewallTargetCreate,
    VmFirewallTargetOut,
)
from app.database import get_db
from app.models.db import AppConfig, HetznerProject, User, VmConfig, VmFirewallTarget

router = APIRouter(prefix="/config", tags=["config"])


# ---------------------------------------------------------------------------
# VM Configs
# ---------------------------------------------------------------------------

@router.get("/vm-configs")
async def list_vm_configs(
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    result = await db.execute(select(VmConfig))
    configs = result.scalars().all()
    return JSONResponse({"vm_configs": [VmConfigOut.model_validate(c).model_dump() for c in configs]})


@router.post("/vm-configs", status_code=201)
async def create_vm_config(
    body: VmConfigCreate,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    # Check for duplicate vm_name
    existing = await db.execute(select(VmConfig).where(VmConfig.vm_name == body.vm_name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"VM config for '{body.vm_name}' already exists.")

    config = VmConfig(vm_name=body.vm_name, domain=body.domain, preferred_server_type=body.preferred_server_type)
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return JSONResponse(VmConfigOut.model_validate(config).model_dump(), status_code=201)


@router.put("/vm-configs/{config_id}")
async def update_vm_config(
    config_id: int,
    body: VmConfigUpdate,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    result = await db.execute(select(VmConfig).where(VmConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail=f"VM config {config_id} not found.")
    config.domain = body.domain
    config.preferred_server_type = body.preferred_server_type
    await db.commit()
    await db.refresh(config)
    return JSONResponse(VmConfigOut.model_validate(config).model_dump())


@router.put("/vm-configs/by-name/{vm_name}")
async def upsert_vm_config_by_name(
    vm_name: str,
    body: VmConfigUpdate,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Create or update a VM config identified by vm_name (upsert)."""
    result = await db.execute(select(VmConfig).where(VmConfig.vm_name == vm_name))
    config = result.scalar_one_or_none()
    if config is None:
        config = VmConfig(vm_name=vm_name, domain=body.domain, preferred_server_type=body.preferred_server_type)
        db.add(config)
    else:
        config.domain = body.domain
        config.preferred_server_type = body.preferred_server_type
    await db.commit()
    await db.refresh(config)
    return JSONResponse(VmConfigOut.model_validate(config).model_dump())


@router.delete("/vm-configs/{config_id}", status_code=204)
async def delete_vm_config(
    config_id: int,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(select(VmConfig).where(VmConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail=f"VM config {config_id} not found.")
    await db.delete(config)
    await db.commit()


# ---------------------------------------------------------------------------
# App Configs
# ---------------------------------------------------------------------------

@router.get("/app")
async def list_app_configs(
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    result = await db.execute(select(AppConfig))
    configs = result.scalars().all()
    return JSONResponse({"app_configs": [AppConfigOut.model_validate(c).model_dump() for c in configs]})


@router.put("/app/{key}")
async def update_app_config(
    key: str,
    body: AppConfigUpdate,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    result = await db.execute(select(AppConfig).where(AppConfig.key == key))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail=f"App config key '{key}' not found.")
    config.value = body.value
    await db.commit()
    await db.refresh(config)
    return JSONResponse(AppConfigOut.model_validate(config).model_dump())


# ---------------------------------------------------------------------------
# VM Firewall Targets
# ---------------------------------------------------------------------------

def _target_out(target: VmFirewallTarget) -> dict:
    return VmFirewallTargetOut(
        id=target.id,
        vm_name=target.vm_name,
        project_id=target.project_id,
        project_name=target.project.name,
        firewall_name=target.firewall_name,
    ).model_dump()


@router.get("/vm-configs/by-name/{vm_name}/firewall-targets")
async def list_firewall_targets(
    vm_name: str,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    result = await db.execute(
        select(VmFirewallTarget)
        .where(VmFirewallTarget.vm_name == vm_name)
        .options(selectinload(VmFirewallTarget.project))
    )
    targets = result.scalars().all()
    return JSONResponse({"targets": [_target_out(t) for t in targets]})


@router.post("/vm-configs/by-name/{vm_name}/firewall-targets", status_code=201)
async def add_firewall_target(
    vm_name: str,
    body: VmFirewallTargetCreate,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    project = await db.get(HetznerProject, body.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    existing = await db.execute(
        select(VmFirewallTarget).where(
            VmFirewallTarget.vm_name == vm_name,
            VmFirewallTarget.project_id == body.project_id,
            VmFirewallTarget.firewall_name == body.firewall_name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Firewall target already exists.")

    target = VmFirewallTarget(
        vm_name=vm_name,
        project_id=body.project_id,
        firewall_name=body.firewall_name,
    )
    db.add(target)
    await db.commit()
    await db.refresh(target)
    # reload with relationship
    await db.refresh(target, ["project"])
    return JSONResponse(_target_out(target), status_code=201)


@router.delete("/vm-configs/by-name/{vm_name}/firewall-targets/{target_id}", status_code=204)
async def delete_firewall_target(
    vm_name: str,
    target_id: int,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(VmFirewallTarget).where(
            VmFirewallTarget.id == target_id,
            VmFirewallTarget.vm_name == vm_name,
        )
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Firewall target not found.")
    await db.delete(target)
    await db.commit()

