"""Pytest fixtures for integration tests.

Uses a real PostgreSQL test database (DATABASE_URL_TEST) so that we exercise Alembic
migrations and the actual async engine, not SQLite or in-memory fakes.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.settings import settings
from app.database import get_db
from app.main import app
from app.models.db import Base

# --------------------------------------------------------------------------- #
# Test engine + session pointing at DATABASE_URL_TEST
# --------------------------------------------------------------------------- #

_test_engine = create_async_engine(settings.DATABASE_URL_TEST, echo=False, pool_pre_ping=True)
_test_session_factory = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
async def create_tables() -> None:  # type: ignore[misc]
    """Create all tables in the test DB once per session."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture()
async def db_session() -> AsyncSession:  # type: ignore[misc]
    """Provide a scoped async session for a single test; rolls back after each test."""
    async with _test_session_factory() as session:
        yield session


@pytest.fixture()
async def admin_user(db_session: AsyncSession) -> None:  # type: ignore[misc]
    """Insert an admin user into the test DB using a known password hash."""
    from passlib.context import CryptContext

    ctx = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")
    hashed = ctx.hash("testpassword")
    await db_session.execute(
        text(
            "INSERT INTO users (username, password_hash) VALUES ('admin', :hash) "
            "ON CONFLICT (username) DO UPDATE SET password_hash = :hash"
        ),
        {"hash": hashed},
    )
    await db_session.commit()


@pytest.fixture()
async def client(admin_user: None) -> AsyncClient:  # type: ignore[misc]  # noqa: ARG001
    """HTTP test client using the ASGI transport — no live server required."""

    async def override_get_db() -> AsyncSession:  # type: ignore[misc]
        async with _test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture()
async def authenticated_client(client: AsyncClient) -> AsyncClient:  # type: ignore[misc]
    """Test client with a valid auth cookie already set."""
    resp = await client.post("/auth/token", json={"username": "admin", "password": "testpassword"})
    assert resp.status_code == 200
    return client
