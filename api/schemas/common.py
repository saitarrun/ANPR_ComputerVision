"""Common schemas."""
from typing import Any, Optional, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class ErrorResponse(BaseModel):
    """Error response."""

    error: dict[str, Any]

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Invalid request",
                    "details": {},
                }
            }
        }


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response."""

    items: list[T]
    next_cursor: Optional[str] = None
    total: Optional[int] = None

    class Config:
        """Pydantic config."""
        json_encoders = {object: str}
