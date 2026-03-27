from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Hetzner Cloud
    HETZNER_API_TOKEN: str = ""
    HETZNER_FIREWALL_NAME: str = ""

    # Cloudflare
    CLOUDFLARE_API_TOKEN: str = ""
    CLOUDFLARE_ZONE_ID: str = ""   # preferred: paste from Cloudflare dashboard (bypasses zone lookup)
    CLOUDFLARE_ZONE_NAME: str = ""  # fallback: used to look up zone ID via API (needs Zone:Read)

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/hetzner_vm_ui"
    DATABASE_URL_TEST: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/hetzner_vm_ui_test"
    )

    # JWT
    SECRET_KEY: str = "changeme"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # IP reflection
    IP_REFLECTION_URL: str = "https://api.ipify.org?format=json"

    # Admin (only used by seed.py — not needed at runtime)
    ADMIN_PASSWORD: str = ""

    # Set to False when running over plain HTTP (e.g. local Docker)
    SECURE_COOKIES: bool = True

    # Logging level for uvicorn and the app (DEBUG, INFO, WARNING, ERROR)
    LOG_LEVEL: str = "info"


settings = Settings()
