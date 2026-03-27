from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.auth.service import get_current_user
from app.lib.ip import detect_public_ip
from app.models.db import User

router = APIRouter(prefix="/ip", tags=["ip"])


@router.get("")
async def get_ip(
    request: Request,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
) -> JSONResponse:
    """Return the caller's detected public IP address."""
    ip = await detect_public_ip(request)
    return JSONResponse({"ip": ip})
