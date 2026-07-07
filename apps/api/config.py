"""Runtime configuration (12-factor). Values come from env / .env."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    default_tenant: str = "demo"
    confidence_threshold: float = 0.75
    inference_mode: str = "mock"


settings = Settings()
