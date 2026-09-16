"""Application configuration loaded from environment.

Central settings object. Nothing (retention, policies, schedules) that belongs to an
organization is hard-coded here; this is infrastructure/runtime config only.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Remote Workforce Monitoring"
    environment: str = "development"
    debug: bool = True

    # Security
    secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 14

    # Datastores
    database_url: str = "postgresql+asyncpg://rwm:rwm@localhost:5432/rwm"
    redis_url: str = "redis://localhost:6379/0"

    # Object storage
    storage_endpoint: str = "http://localhost:9000"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    storage_bucket: str = "rwm-screenshots"

    # CORS
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
