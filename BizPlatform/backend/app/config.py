"""Application settings, loaded from environment variables (never hard-coded secrets)."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BIZ_", extra="ignore")

    env: str = "production"  # production | development | test
    database_url: str = "sqlite:///./dev.db"
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt sensitive columns.
    encryption_key: str = Field(..., min_length=44)
    # Sessions
    session_idle_minutes: int = 30
    session_absolute_hours: int = 12
    cookie_secure: bool = True
    # Brute-force protection
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    login_rate_per_minute: int = 10
    # Require every user to enable 2FA before using the system
    require_2fa: bool = False
    vat_rate: float = 18.0
    org_name: str = "BizPlatform"

    @property
    def is_dev(self) -> bool:
        return self.env in ("development", "test")


@lru_cache
def get_settings() -> Settings:
    return Settings()
