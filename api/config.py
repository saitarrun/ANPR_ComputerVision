"""Application configuration from environment variables."""
import os
from enum import Enum
from typing import Literal

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, ConfigDict


class UserRole(str, Enum):
    """User roles for RBAC."""

    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class Environment(str, Enum):
    """Deployment environment."""

    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings from environment variables."""

    model_config = ConfigDict(extra="ignore", env_file=".env", case_sensitive=False)

    # ---- App ----
    app_env: Environment = Field(default=Environment.DEV, validation_alias="ANPR_ENV")
    api_host: str = Field(default="0.0.0.0", validation_alias="API_HOST")
    api_port: int = Field(default=8000, validation_alias="API_PORT")
    api_title: str = Field(default="ANPR Backend API", validation_alias="API_TITLE")
    api_version: str = Field(default="0.1.0", validation_alias="API_VERSION")

    # ---- Auth ----
    jwt_secret: str = Field(..., validation_alias="JWT_SECRET", min_length=32)
    jwt_algorithm: Literal["HS256", "RS256"] = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=60, validation_alias="JWT_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, validation_alias="JWT_REFRESH_EXPIRY_DAYS")

    # ---- Encryption ----
    fernet_key: str = Field(default="", validation_alias="FERNET_KEY")
    celery_encryption_key: str = Field(..., validation_alias="CELERY_ENCRYPTION_KEY", min_length=44)

    # ---- Database ----
    database_url: str = Field(..., validation_alias="DATABASE_URL")
    db_pool_size: int = Field(default=20)
    db_max_overflow: int = Field(default=40)
    db_pool_timeout: int = Field(default=30)

    # ---- Redis ----
    redis_url: str = Field(..., validation_alias="REDIS_URL")

    # ---- S3 / MinIO ----
    s3_endpoint_url: str = Field(..., validation_alias="S3_ENDPOINT_URL")
    s3_access_key: str = Field(..., validation_alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(..., validation_alias="S3_SECRET_KEY")
    s3_region: str = Field(default="us-east-1", validation_alias="S3_REGION")
    s3_bucket_crops: str = Field(default="anpr-crops", validation_alias="S3_BUCKET_CROPS")
    s3_bucket_frames: str = Field(default="anpr-frames", validation_alias="S3_BUCKET_FRAMES")
    s3_bucket_audit: str = Field(default="anpr-audit", validation_alias="S3_BUCKET_AUDIT")

    # ---- Celery ----
    celery_broker_url: str | None = Field(default=None, validation_alias="CELERY_BROKER_URL")
    celery_result_backend: str | None = Field(default=None, validation_alias="CELERY_BACKEND_URL")

    # ---- Pipeline Config ----
    target_fps: int = Field(default=15, validation_alias="TARGET_FPS")
    confidence_plate: float = Field(default=0.75, validation_alias="CONFIDENCE_PLATE")
    confidence_char: float = Field(default=0.60, validation_alias="CONFIDENCE_CHAR")
    track_vote_window: int = Field(default=8, validation_alias="TRACK_VOTE_WINDOW")

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v


def get_settings() -> Settings:
    """Get settings singleton."""
    return Settings()  # type: ignore


settings = get_settings()
