from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="FiberOps CRM", alias="APP_NAME")
    app_env: str = Field(default="dev", alias="APP_ENV")
    app_release: str = Field(default="local", alias="APP_RELEASE")

    database_url: str = Field(
        default="postgresql+asyncpg://fiber:fiberpass@localhost:5432/fibercrm",
        alias="DATABASE_URL",
    )
    jwt_secret: str = Field(default="change-me", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    cors_allow_origins: str = Field(default="*", alias="CORS_ALLOW_ORIGINS")
    sql_echo: bool = Field(default=False, alias="SQL_ECHO")
    seed_demo_data: bool = Field(default=True, alias="SEED_DEMO_DATA")

    sentry_dsn: str | None = Field(default=None, alias="SENTRY_DSN")
    sentry_environment: str | None = Field(default=None, alias="SENTRY_ENVIRONMENT")
    sentry_traces_sample_rate: float = Field(default=0.0, alias="SENTRY_TRACES_SAMPLE_RATE")

    rate_limit_enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    rate_limit_auth_per_minute: int = Field(default=10, alias="RATE_LIMIT_AUTH_PER_MINUTE")
    rate_limit_register_per_minute: int = Field(default=5, alias="RATE_LIMIT_REGISTER_PER_MINUTE")
    rate_limit_report_per_minute: int = Field(default=12, alias="RATE_LIMIT_REPORT_PER_MINUTE")
    rate_limit_realtime_per_minute: int = Field(default=90, alias="RATE_LIMIT_REALTIME_PER_MINUTE")

    max_upload_bytes: int = Field(default=2_000_000, alias="MAX_UPLOAD_BYTES")

    backup_retention_days: int = Field(default=14, alias="BACKUP_RETENTION_DAYS")
    backup_interval_seconds: int = Field(default=86_400, alias="BACKUP_INTERVAL_SECONDS")

    @property
    def cors_origins(self) -> list[str]:
        raw = [item.strip() for item in self.cors_allow_origins.split(",") if item.strip()]
        return raw or ["*"]

    @property
    def is_production_like(self) -> bool:
        return self.app_env.lower() in {"prod", "production", "staging"}

    @model_validator(mode="after")
    def validate_security_defaults(self) -> "Settings":
        if not self.is_production_like:
            return self
        if self.jwt_secret in {"", "change-me", "super-secret-key"}:
            raise ValueError("JWT_SECRET must be set to a strong value outside dev")
        if "*" in self.cors_origins:
            raise ValueError("CORS_ALLOW_ORIGINS cannot contain wildcard in production-like environments")
        if self.seed_demo_data:
            raise ValueError("SEED_DEMO_DATA must be false in production-like environments")
        return self


settings = Settings()
