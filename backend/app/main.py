from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.config.router import router as config_router
from app.firewall.router import router as firewall_router
from app.ip.router import router as ip_router
from app.vms.router import router as vms_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup — add initialization logic here (e.g., DB pool warm-up)
    yield
    # Shutdown — clean up resources here


app = FastAPI(
    title="Hetzner VM Management API",
    description="Backend API for the Hetzner Cloud VM Management UI",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(vms_router)
app.include_router(ip_router)
app.include_router(firewall_router)
app.include_router(config_router)
