"""Authentication schemas."""
from pydantic import BaseModel


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

    class Config:
        """Pydantic config."""
        from_attributes = True
