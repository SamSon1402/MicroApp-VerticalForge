"""Settings."""
from functools import lru_cache

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_port: int = 8000
    log_level: str = "INFO"

    oidc_issuer: str
    oidc_jwks_url: HttpUrl
    oidc_audience: str

    pack_signing_secret: str = Field(..., min_length=8)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
