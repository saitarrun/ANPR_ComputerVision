"""Configuration for ANPR API."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """API settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql+asyncpg://anpr:anpr_dev_pw@localhost:5432/anpr"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_title: str = "ANPR API"
    api_version: str = "0.1.0"
    api_debug: bool = False

    # JWT Authentication
    jwt_secret: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 7

    # Encryption (Fernet)
    fernet_key: str = ""  # Must be set from env

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # S3 / MinIO
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_region: str = "us-east-1"
    s3_bucket: str = "anpr"

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
