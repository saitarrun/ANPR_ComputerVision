"""FastAPI application factory and middleware setup."""

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
import logging
import uuid
import uvicorn
import os

from api.config import settings
from api.exceptions import ANPRException
from api.logging import audit_log_context, audit_logger
from api.rate_limiter import limiter
from db.engine import init_db, close_db
from api.routers import auth, ingest, websocket, data, debug, watchlist, review, audit, settings as settings_router

logger = logging.getLogger(__name__)


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect HTTP to HTTPS in production."""

    async def dispatch(self, request: Request, call_next):
        if settings.app_env.value == "production":
            if request.url.scheme == "http":
                url = request.url.replace(scheme="https")
                return JSONResponse(
                    status_code=301,
                    content={"error": "Moved Permanently"},
                    headers={"Location": str(url)},
                )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # HSTS (HTTP Strict-Transport-Security)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Deny embedding in frames
        response.headers["X-Frame-Options"] = "DENY"
        
        # Content Security Policy: restrict to same-origin resources
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        
        # Prevent referrer leaking
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to set audit logging context and log security events."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        client_ip = request.client.host if request.client else "unknown"
        
        # Extract user ID from JWT if available
        user_id = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from api.security import decode_jwt
                token = auth_header[7:]
                payload = decode_jwt(token, settings.jwt_secret)
                user_id = payload.get("sub")
            except Exception:
                pass  # Invalid token; will be handled by route auth

        with audit_log_context(request_id, user_id, client_ip):
            request.state.request_id = request_id
            request.state.user_id = user_id
            request.state.client_ip = client_ip
            
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            
            # Log auth attempts
            if request.url.path == "/v1/auth/login" and request.method == "POST":
                audit_logger.info(
                    "login_attempt",
                    extra={
                        "action": "login_attempt",
                        "status": response.status_code,
                        "resource": "auth/login",
                    }
                )
            
            # Log token refreshes
            if request.url.path == "/v1/auth/refresh" and request.method == "POST":
                audit_logger.info(
                    "token_refresh",
                    extra={
                        "action": "token_refresh",
                        "status": response.status_code,
                        "resource": "auth/refresh",
                    }
                )
            
            return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown event handler."""
    logger.info("Starting ANPR API...")
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    yield

    logger.info("Shutting down ANPR API...")
    await close_db()


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # State: rate limiter
    app.state.limiter = limiter

    # CORS middleware: Parse explicit origins from env; reject wildcard + credentials combo
    frontend_origins = os.getenv("FRONTEND_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
    frontend_origins = [origin.strip() for origin in frontend_origins if origin.strip()]

    # Security: Never allow wildcard with credentials
    if "*" in frontend_origins and len(frontend_origins) > 1:
        frontend_origins = [o for o in frontend_origins if o != "*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=frontend_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # Security middleware (order matters: add from last to first)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(AuditLoggingMiddleware)

    # Request ID middleware
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    # Rate limit exceeded handler
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many requests. Please retry after some time.",
                    "details": {"retry_after": 60},
                }
            },
            headers={"Retry-After": "60"},
        )

    # Health check endpoints
    @app.get("/healthz", tags=["health"])
    async def health() -> dict:
        """Liveness check."""
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    async def readiness() -> dict:
        """Readiness check (DB + Redis)."""
        try:
            from db.engine import engine
            async with engine.begin() as conn:
                await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            return {"status": "ready"}
        except Exception as e:
            logger.error(f"Readiness check failed: {e}")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service unavailable") from e

    # Exception handlers
    @app.exception_handler(ANPRException)
    async def anpr_exception_handler(request: Request, exc: ANPRException):
        request_id = getattr(request.state, "request_id", "unknown")
        user_id = getattr(request.state, "user_id", None)
        logger.warning(f"ANPR Exception: {exc.code} - {exc.message}", extra={"request_id": request_id})
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.error(f"Unhandled exception: {str(exc)}", exc_info=exc, extra={"request_id": request_id})

        # Return specific error messages for common exception types
        exc_type = type(exc).__name__
        if "asyncpg" in exc_type.lower() or "postgresql" in str(exc).lower():
            message = "Database connection failed. Please try again in a few moments."
            status_code = 503
        elif "validation" in exc_type.lower():
            message = "Invalid input provided. Please check your request."
            status_code = 422
        elif "permission" in exc_type.lower() or "unauthorized" in str(exc).lower():
            message = "You do not have permission to perform this action."
            status_code = 403
        else:
            message = "An unexpected error occurred. Please contact support with request ID: " + request_id
            status_code = 500

        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": exc_type, "message": message, "details": {"request_id": request_id}}},
            headers={"X-Request-ID": request_id},
        )

    # Include routers with rate limiting
    app.include_router(auth.router)
    app.include_router(ingest.router)
    app.include_router(websocket.router)
    app.include_router(data.router)
    app.include_router(watchlist.router)
    app.include_router(review.router)
    app.include_router(audit.router)
    app.include_router(settings_router.router)
    if settings.app_env.value != "production":
        app.include_router(debug.router)

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
