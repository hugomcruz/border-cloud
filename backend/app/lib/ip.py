"""IP detection utility — detect_public_ip()."""

import httpx
from fastapi import HTTPException, Request

from app.settings import settings


async def detect_public_ip(request: Request) -> str:
    """Detect the caller's public IP address.

    Priority:
    1. X-Forwarded-For header (first entry) — set by load balancers/proxies
    2. HTTP GET to settings.IP_REFLECTION_URL (e.g., ipify) — parses {"ip": "..."}

    Raises HTTPException(503) if IP cannot be determined.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(settings.IP_REFLECTION_URL)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=503,
                detail="Unable to detect your public IP at this time.",
            )
        return str(resp.json()["ip"])
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to detect your public IP at this time.",
        ) from exc
