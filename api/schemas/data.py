"""Data schemas for regions, cameras, detections, plates."""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class RegionOut(BaseModel):
    """Region response schema."""

    id: str
    code: str
    name: str
    regex: str
    charset: str
    retention_days: int
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class CameraOut(BaseModel):
    """Camera response schema."""

    id: str
    name: str
    source_type: str
    url: Optional[str] = None
    region_id: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    last_heartbeat: Optional[datetime] = None
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class DetectionOut(BaseModel):
    """Detection response schema."""

    id: str
    camera_id: str
    plate_id: str
    frame_timestamp: datetime
    confidence: float
    bbox: dict
    ocr_backend: str
    quality_score: float
    crop_url: Optional[str] = None
    frame_url: Optional[str] = None
    is_persisted: str
    tracking_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class PlateOut(BaseModel):
    """Plate response schema."""

    id: str
    plate_string: str
    region_id: str
    detection_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    avg_confidence: float
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class WatchlistIn(BaseModel):
    """Watchlist create/update schema."""

    plate_pattern: str
    region_id: str
    reason: Optional[str] = None
    priority: int = 0
    alert_enabled: bool = True
    alert_channel: str = "webhook"


class WatchlistOut(BaseModel):
    """Watchlist response schema."""

    id: str
    plate_pattern: str
    region_id: str
    reason: Optional[str] = None
    priority: int
    alert_enabled: bool
    alert_channel: str
    dedup_window: int
    last_hit: Optional[datetime] = None
    hit_count: int
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
