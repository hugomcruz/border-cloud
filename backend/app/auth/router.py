import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import LoginRequest, TokenResponse, UpdateProfileRequest, UserOut
from app.auth.service import create_access_token, get_current_user, hash_password, verify_password
from app.database import async_session_factory, get_db
from app.limiter import limiter
from app.models.db import HetznerProject, User, UserProjectPermission
from app.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)

_COOKIE_KWARGS = {
    "key": "access_token",
    "httponly": True,
    "secure": settings.SECURE_COOKIES,
    "samesite": "lax",
    "path": "/",
}


def _extract_client_ip(request: Request) -> str | None:
    """Return the real client IP, preferring X-Forwarded-For over the direct connection."""
    import ipaddress

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        candidate = forwarded_for.split(",")[0].strip()
    else:
        candidate = request.headers.get("x-real-ip") or (
            request.client.host if request.client else None
        )
    if not candidate:
        return None
    try:
        addr = ipaddress.ip_address(candidate)
        # Skip private / loopback / link-local addresses
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            return None
        return str(addr)
    except ValueError:
        return None


async def _sync_login_firewall(user_id: int, username: str, ip: str) -> None:
    """Background task: add/replace the user's IP rule in fw-users for every accessible project."""
    from app.lib.hetzner import upsert_user_ip_rule

    async with async_session_factory() as db:
        # Load user to check superadmin status
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user is None:
            return

        if user.is_superadmin:
            proj_result = await db.execute(
                select(HetznerProject).where(HetznerProject.is_active.is_(True))
            )
            projects = list(proj_result.scalars().all())
        else:
            proj_result = await db.execute(
                select(HetznerProject)
                .join(UserProjectPermission, UserProjectPermission.project_id == HetznerProject.id)
                .where(
                    UserProjectPermission.user_id == user_id,
                    HetznerProject.is_active.is_(True),
                )
            )
            projects = list(proj_result.scalars().all())

        for project in projects:
            if not project.firewall_name:
                continue
            try:
                await upsert_user_ip_rule(project.firewall_name, ip, project.api_token, username)
                log.info("[login_fw] updated firewall '%s' for user '%s' ip=%s", project.firewall_name, username, ip)
            except Exception as exc:  # noqa: BLE001
                log.warning("[login_fw] failed to update firewall '%s' for user '%s': %s", project.firewall_name, username, exc)


@router.post("/token", response_model=TokenResponse)
@limiter.limit(settings.LOGIN_RATE_LIMIT)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate and issue a JWT in an httpOnly cookie."""
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalars().first()

    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token({"sub": user.username})
    response.set_cookie(value=token, **_COOKIE_KWARGS)

    # Fire-and-forget: update fw-users firewall rules with the user's real IP
    client_ip = _extract_client_ip(request)
    if client_ip:
        asyncio.create_task(_sync_login_firewall(user.id, user.username, client_ip))
        log.info("[login] user='%s' ip=%s — firewall sync queued", user.username, client_ip)
    else:
        log.info("[login] user='%s' — no public IP detected, skipping firewall sync", user.username)

    return TokenResponse(access_token=token)


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Clear the httpOnly auth cookie."""
    response.set_cookie(value="", max_age=0, **_COOKIE_KWARGS)
    return {"message": "Logged out"}


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    """Return the currently authenticated user's profile."""
    return UserOut.model_validate(current_user)


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Update the current user's name, email, and/or password."""
    if body.new_password is not None:
        if not body.current_password:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="current_password is required to set a new password.",
            )
        if not verify_password(body.current_password, current_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect.",
            )
        current_user.password_hash = hash_password(body.new_password)

    if body.name is not None:
        current_user.name = body.name or None
    if body.email is not None:
        current_user.email = body.email or None

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return UserOut.model_validate(current_user)
