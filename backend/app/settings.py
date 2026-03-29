from pydantic import model_validator
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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # IP reflection
    IP_REFLECTION_URL: str = "https://api.ipify.org?format=json"

    # Admin (only used by seed.py — not needed at runtime)
    ADMIN_PASSWORD: str = ""

    # Set to False when running over plain HTTP (e.g. local Docker)
    SECURE_COOKIES: bool = True

    # Logging level for uvicorn and the app (DEBUG, INFO, WARNING, ERROR)
    LOG_LEVEL: str = "info"

    # Enable Swagger UI / OpenAPI endpoints (disable in production)
    DEBUG: bool = False

    # Login rate limit (slowapi format, e.g. "10/minute")
    LOGIN_RATE_LIMIT: str = "10/minute"

    @model_validator(mode="after")
    def _validate_secret_key(self) -> "Settings":
        if self.SECRET_KEY == "changeme" or len(self.SECRET_KEY) < 32:
            raise ValueError(
                "SECRET_KEY must be set to a random string of at least 32 characters. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return self


settings = Settings()
