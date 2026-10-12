"""Data schemas for regions, cameras, detections, plates."""

from pydantic import BaseModel
from datetime import datetime
from typing import Any, Optional


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
    bbox: dict[str, Any]
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
    confidence: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class WatchlistIn(BaseModel):
    """Watchlist create/update schema."""

    plate_pattern: str
    region_id: Optional[str] = None
    reason: Optional[str] = None
    priority: int = 0
    alert_enabled: bool = True
    alert_channel: str = "webhook"


class WatchlistOut(BaseModel):
    """Watchlist response schema."""

    id: str
    plate_pattern: str
    region_id: Optional[str] = None
    reason: Optional[str] = None
    priority: int
    alert_enabled: bool
    alert_channel: Optional[str] = None
    dedup_window: int
    last_hit: Optional[datetime] = None
    match_count: int
    created_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ReviewQueueOut(BaseModel):
    """Review queue item response schema."""

    id: str
    detection_id: str
    status: str
    reviewer_id: Optional[str] = None
    detection_blob: dict[str, Any]
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ReviewQueueResolve(BaseModel):
    """Review queue resolution schema."""

    action: str  # approve, reject, flag
    notes: Optional[str] = None
    comment: Optional[str] = None
    corrected_plate: Optional[str] = None


class AuditLogOut(BaseModel):
    """Audit log response schema."""

    id: str
    user_id: str
    action: str
    resource_type: str
    resource_id: str
    ip_address: str
    details: dict[str, Any]
    created_at: datetime

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class StreamIn(BaseModel):
    """Stream create schema (backed by the Camera model)."""

    name: str
    rtsp_url: str
    region_id: str


class StreamOut(BaseModel):
    """Stream response schema."""

    id: str
    name: str
    rtsp_url: Optional[str] = None
    region_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    stats: Optional[dict[str, Any]] = None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class StreamListOut(BaseModel):
    """Paginated stream list response."""

    items: list[StreamOut]
    total: int
    limit: int
    offset: int
