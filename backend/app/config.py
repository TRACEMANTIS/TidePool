"""TidePool application configuration via environment variables."""

import warnings

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    APP_NAME: str = "TidePool"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = (
        "postgresql+asyncpg://tidepool:tidepool_dev@localhost:5432/tidepool"
    )
    REDIS_URL: str = "redis://localhost:6379/0"

    # -- Authentication / tokens --------------------------------------------
    SECRET_KEY: str  # No default -- must be set via environment variable.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # -- CORS ---------------------------------------------------------------
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # -- Upload / file handling ---------------------------------------------
    ALLOWED_UPLOAD_EXTENSIONS: list[str] = [".xlsx", ".xls", ".csv"]
    MAX_UPLOAD_SIZE_MB: int = 50
    UPLOAD_DIR: str = "/var/lib/tidepool/uploads"

    # -- Rate limiting ------------------------------------------------------
    RATE_LIMIT_DEFAULT: str = "100/minute"
    RATE_LIMIT_TRACKING: str = "300/minute"
    RATE_LIMIT_AUTH: str = "10/minute"

    # -- Brute-force / lockout ----------------------------------------------
    MAX_LOGIN_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15

    # -- Field-level encryption (Fernet key for SMTP credentials) -----------
    ENCRYPTION_KEY: str  # Must be a valid Fernet key, set via env var.

    # -- Agent / AI integration -----------------------------------------------
    ANTHROPIC_API_KEY: str = ""  # Optional; enables AI-powered pretext generation.
    AGENT_ENABLED: bool = True
    AGENT_AUTO_EXECUTE: bool = False  # Safety: require human approval for auto-start.
    AGENT_MAX_RECIPIENTS_AUTO: int = 1000  # Max recipients for auto-executed campaigns.
    MCP_SERVER_ENABLED: bool = True

    # -- Campaign header signing (mail gateway allowlisting) -----
    TIDEPOOL_HEADER_ENABLED: bool = True
    TIDEPOOL_HEADER_SECRET: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @model_validator(mode="after")
    def warn_header_secret_empty(self) -> "Settings":
        if self.TIDEPOOL_HEADER_ENABLED and not self.TIDEPOOL_HEADER_SECRET:
            warnings.warn(
                "TIDEPOOL_HEADER_ENABLED is True but TIDEPOOL_HEADER_SECRET is "
                "empty. X-TidePool-Campaign-ID headers will be unsigned.",
                UserWarning,
                stacklevel=2,
            )
        return self

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if v == "change-me-in-production":
            raise ValueError(
                "SECRET_KEY must not be the placeholder value "
                "'change-me-in-production'. Set a strong secret."
            )
        if len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters long."
            )
        return v


settings = Settings()
