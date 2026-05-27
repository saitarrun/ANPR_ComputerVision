"""Pydantic settings for all environment configuration."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # App
    anpr_env: str = "dev"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 2

    # Auth + Security
    # JWT secret (min 32 chars): Generate with secrets.token_urlsafe(32)
    jwt_secret: str = Field(default="change-me-dev-only-jwt-secret-32plus-bytes", env="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Fernet key (44 chars base64): Generate with Fernet.generate_key().decode()
    fernet_key: str = Field(default="", env="FERNET_KEY")

    # Password hashing: bcrypt with cost 12 (see security.py)
    # No env vars needed; configured in pwd_context

    # Database
    database_url: str = "postgresql+asyncpg://anpr:anpr_dev_pw@localhost:5432/anpr"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "anpr"
    postgres_password: str = "anpr_dev_pw"
    postgres_db: str = "anpr"

    # Redis (for rate limiting, token blacklist, session cache)
    redis_url: str = "redis://localhost:6379/0"

    # MinIO / S3
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "anpr_admin"
    s3_secret_key: str = "anpr_dev_pw"
    s3_region: str = "us-east-1"
    s3_bucket_crops: str = "anpr-crops"
    s3_bucket_frames: str = "anpr-frames"
    s3_bucket_audit: str = "anpr-audit"

    # Observability
    prometheus_multiproc_dir: str = "/tmp/prom-multi"
    otel_exporter_otlp_endpoint: str = ""

    # Models
    detector_weights: str = "models/plate_yolov8s.pt"
    ocr_backend: str = "paddle"
    paddle_ocr_lang: str = "en"
    mlflow_tracking_uri: str = ""

    # Pipeline
    target_fps: int = 15
    confidence_plate: float = 0.75
    confidence_char: float = 0.60
    track_vote_window: int = 8

    # Ingest
    webcam_index: int = 0
    iphone_source: str = "continuity"
    iphone_rtsp_url: str = "rtsp://192.168.0.50:8080/video"
    rtsp_reconnect_backoff_sec: int = 2
    rtsp_reconnect_max_sec: int = 60

    # Alerts
    alert_webhook_url: str = ""
    alert_dedup_window_sec: int = 300

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
