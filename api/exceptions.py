"""Custom exception classes for ANPR API."""
from typing import Any, Optional


class ANPRException(Exception):
    """Base exception for ANPR API."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[dict[str, Any]] = None,
    ):
        """Initialize exception.

        Args:
            code: Error code (e.g., "VALIDATION_ERROR")
            message: Human-readable message
            status_code: HTTP status code
            details: Additional error details
        """
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class ValidationError(ANPRException):
    """Validation error (422)."""

    def __init__(
        self,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ):
        """Initialize validation error."""
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=422,
            details=details,
        )


class AuthenticationError(ANPRException):
    """Authentication error (401)."""

    def __init__(self, message: str):
        """Initialize authentication error."""
        super().__init__(
            code="AUTHENTICATION_ERROR",
            message=message,
            status_code=401,
            details={},
        )


class AuthorizationError(ANPRException):
    """Authorization error (403)."""

    def __init__(self, message: str = "Insufficient permissions"):
        """Initialize authorization error."""
        super().__init__(
            code="AUTHORIZATION_ERROR",
            message=message,
            status_code=403,
            details={},
        )


class NotFoundError(ANPRException):
    """Resource not found (404)."""

    def __init__(self, resource: str, resource_id: str):
        """Initialize not found error."""
        super().__init__(
            code="NOT_FOUND",
            message=f"{resource} with id {resource_id} not found",
            status_code=404,
            details={"resource": resource, "resource_id": resource_id},
        )


class ConflictError(ANPRException):
    """Resource conflict (409)."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        """Initialize conflict error."""
        super().__init__(
            code="CONFLICT",
            message=message,
            status_code=409,
            details=details,
        )


class RateLimitError(ANPRException):
    """Rate limit exceeded (429)."""

    def __init__(self, retry_after: int = 60):
        """Initialize rate limit error."""
        super().__init__(
            code="RATE_LIMIT_EXCEEDED",
            message="Too many requests. Please try again later.",
            status_code=429,
            details={"retry_after": retry_after},
        )


class DatabaseError(ANPRException):
    """Database error (500)."""

    def __init__(self, message: str = "Database operation failed"):
        """Initialize database error."""
        super().__init__(
            code="DATABASE_ERROR",
            message=message,
            status_code=500,
            details={},
        )
