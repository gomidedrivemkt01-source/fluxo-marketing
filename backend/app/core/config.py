from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_prefix="APP_",
        extra="ignore",
    )

    env: Literal["development", "test", "production"] = "development"
    name: str = "Fluxo Marketing"
    public_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8000")
    database_url: SecretStr
    session_secret: SecretStr = Field(min_length=32)
    token_encryption_key: SecretStr = Field(min_length=32)
    supabase_url: AnyHttpUrl
    supabase_publishable_key: SecretStr
    bootstrap_organization_name: str = "Marketing"
    cookie_secure: bool = False
    allowed_origins: list[str] = ["http://localhost:5173"]

    @field_validator("allowed_origins")
    @classmethod
    def reject_wildcard_origins(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError("CORS wildcard is not allowed")
        return value

    @model_validator(mode="after")
    def require_secure_production_settings(self) -> "Settings":
        if self.env == "production" and not self.cookie_secure:
            raise ValueError("APP_COOKIE_SECURE must be true in production")
        if self.env == "production" and str(self.public_url).startswith("http://"):
            raise ValueError("APP_PUBLIC_URL must use HTTPS in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
