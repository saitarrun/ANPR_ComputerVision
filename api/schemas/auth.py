"""Authentication schemas."""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class LoginRequest(BaseModel):
    """Login request."""

    email: str
    password: str


class TokenResponse(BaseModel):
    """Token response."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # Seconds


class UserResponse(BaseModel):
    """User response."""

    id: str
    email: str
    username: str
    role: str
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        """Pydantic config."""
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class ChangePasswordRequest(BaseModel):
    """Change password request."""

    current_password: str
    new_password: str
    confirm_password: str


class UserSettingsOut(BaseModel):
    """User settings response."""

    id: str
    email: str
    retention_days: int
    alert_channels: list[str]
    export_redaction_enabled: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class UserSettingsUpdate(BaseModel):
    """User settings update request."""

    retention_days: Optional[int] = None
    alert_channels: Optional[list[str]] = None
    export_redaction_enabled: Optional[bool] = None


class AdminUserListItem(BaseModel):
    """Admin user list item."""

    id: str
    email: str
    username: str
    role: str
    created_at: datetime
    last_login: Optional[datetime] = None
    is_active: bool

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class AdminUserUpdate(BaseModel):
    """Admin user update request."""

    role: Optional[str] = None
    is_active: Optional[bool] = None
