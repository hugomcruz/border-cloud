from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import get_current_user
from app.config.schemas import (
    AppConfigOut,
    AppConfigUpdate,
    VmConfigCreate,
    VmConfigOut,
    VmConfigUpdate,
)
from app.database import get_db
from app.models.db import AppConfig, User, VmConfig

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
