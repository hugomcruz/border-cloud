"""Idempotent seed script — creates the admin user and default app_configs.

Usage:
    cd backend/
    python -m scripts.seed
"""
import asyncio
import os
import sys

import bcrypt as _bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Allow running from backend/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.settings import settings  # noqa: E402

DEFAULT_APP_CONFIGS = [
    ("hetzner_default_server_type", "cx23"),
    ("hetzner_default_location", "nbg1"),
    ("hetzner_default_ssh_key", ""),
]


async def seed() -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session_factory() as session:
        # Create admin user (idempotent)
        admin_password = settings.ADMIN_PASSWORD
        if not admin_password:
            print("WARNING: ADMIN_PASSWORD env var is not set — skipping admin user creation.")
        else:
            password_hash = _bcrypt.hashpw(admin_password.encode(), _bcrypt.gensalt(rounds=12)).decode()
            await session.execute(
                text(
                    "INSERT INTO users (username, password_hash, is_superadmin) VALUES (:username, :hash, true) "
                    "ON CONFLICT (username) DO UPDATE SET is_superadmin = true"
                ),
                {"username": "admin", "hash": password_hash},
            )
            print("Admin user: upserted as superadmin.")

        # Insert default app_configs — update the value only if the existing row is blank
        for key, default_value in DEFAULT_APP_CONFIGS:
            await session.execute(
                text(
                    "INSERT INTO app_configs (key, value) VALUES (:key, :value) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value "
                    "WHERE app_configs.value = ''"
                ),
                {"key": key, "value": default_value},
            )
        print("App configs: seeded (existing rows untouched).")

        # Create default Hetzner project from env vars if token is configured
        if settings.HETZNER_API_TOKEN:
            await session.execute(
                text(
                    "INSERT INTO hetzner_projects (name, api_token, firewall_name) "
                    "VALUES (:name, :token, :firewall) "
                    "ON CONFLICT (name) DO NOTHING"
                ),
                {
                    "name": "default",
                    "token": settings.HETZNER_API_TOKEN,
                    "firewall": settings.HETZNER_FIREWALL_NAME,
                },
            )
            print("Default Hetzner project: seeded (skipped if already exists).")
        else:
            print("WARNING: HETZNER_API_TOKEN not set — skipping default project creation.")

        await session.commit()

    await engine.dispose()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
