"""FastAPI application factory and middleware setup."""

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import uuid
import uvicorn

from api.config import settings
from api.exceptions import ANPRException
from db.engine import init_db, close_db
from api.routers import auth, ingest, websocket, data, debug, watchlist, review, audit

logger = logging.getLogger(__name__)


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

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request ID middleware
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

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
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred", "details": {}}},
            headers={"X-Request-ID": request_id},
        )

    # Include routers
    app.include_router(auth.router)
    app.include_router(ingest.router)
    app.include_router(websocket.router)
    app.include_router(data.router)
    app.include_router(watchlist.router)
    app.include_router(review.router)
    app.include_router(audit.router)
    if settings.app_env.value != "production":
        app.include_router(debug.router)

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)

