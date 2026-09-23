from functools import lru_cache
from typing import Literal
from urllib.parse import quote

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
    database_url: SecretStr | None = None
    database_host: str | None = None
    database_port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = "postgres"
    database_user: str | None = None
    database_password: SecretStr | None = None
    database_sslmode: Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"] = (
        "require"
    )
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
        if not self.database_url and not all(
            [self.database_host, self.database_user, self.database_password]
        ):
            raise ValueError(
                "Configure APP_DATABASE_URL ou host, usuário e senha separados para o banco."
            )
        if self.env == "production" and not self.cookie_secure:
            raise ValueError("APP_COOKIE_SECURE must be true in production")
        if self.env == "production" and str(self.public_url).startswith("http://"):
            raise ValueError("APP_PUBLIC_URL must use HTTPS in production")
        return self

    def database_dsn(self) -> str:
        if self.database_url:
            return self.database_url.get_secret_value()
        assert self.database_host is not None
        assert self.database_user is not None
        assert self.database_password is not None
        user = quote(self.database_user, safe="")
        password = quote(self.database_password.get_secret_value(), safe="")
        name = quote(self.database_name, safe="")
        return (
            f"postgresql+psycopg://{user}:{password}@{self.database_host}:"
            f"{self.database_port}/{name}?sslmode={self.database_sslmode}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
