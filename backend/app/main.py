from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
import logging

from fastapi import FastAPI, Request
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.admin.router import router as admin_router
from app.auth.router import router as auth_router
from app.config.router import router as config_router
from app.firewall.router import router as firewall_router
from app.ip.router import router as ip_router
from app.limiter import limiter
from app.projects.router import router as projects_router
from app.settings import settings
from app.vms.router import router as vms_router

logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(levelname)-8s %(name)s — %(message)s",
)


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        return response


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
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(_SecurityHeadersMiddleware)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(projects_router)
app.include_router(vms_router)
app.include_router(ip_router)
app.include_router(firewall_router)
app.include_router(config_router)
