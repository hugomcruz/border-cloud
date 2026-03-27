from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import LoginRequest, TokenResponse
from app.auth.service import create_access_token, verify_password
from app.database import get_db
from app.models.db import User
from app.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_KWARGS = {
    "key": "access_token",
    "httponly": True,
    "secure": settings.SECURE_COOKIES,
    "samesite": "lax",
    "path": "/",
}


@router.post("/token", response_model=TokenResponse)
async def login(
    body: LoginRequest,
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
    return TokenResponse(access_token=token)


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Clear the httpOnly auth cookie."""
    response.set_cookie(value="", max_age=0, **_COOKIE_KWARGS)
    return {"message": "Logged out"}
