"""FastAPI application for ANPR system."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from api.settings import settings
from db.core import Database

logger = logging.getLogger(__name__)

# Initialize database
db = Database(settings.database_url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle app startup and shutdown events.

    Startup:
    - Test database connectivity
    - Run migrations (via Alembic)

    Shutdown:
    - Close database connections
    """
    # Startup
    logger.info("ANPR API starting up...")

    # Health check
    if await db.health_check():
        logger.info("Database connection successful")
    else:
        logger.error("Database health check failed")
        raise RuntimeError("Cannot connect to database")

    yield

    # Shutdown
    logger.info("ANPR API shutting down...")
    await db.close()


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        FastAPI application instance.
    """
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        debug=settings.api_debug,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: restrict to known origins in prod
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check endpoints
    @app.get("/healthz", tags=["health"])
    async def health() -> dict:
        """Liveness check (app is running)."""
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    async def readiness() -> dict:
        """Readiness check (app can serve requests)."""
        try:
            if await db.health_check():
                return {"status": "ready"}
            else:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Database unavailable",
                )
        except Exception as e:
            logger.error(f"Readiness check failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service unavailable",
            ) from e

    # Exception handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc):
        return {
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": exc.detail,
            }
        }

    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc):
        logger.error(f"Unhandled exception: {exc}")
        return {
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
            }
        }

    return app


# Create app instance
app = create_app()


async def run() -> None:
    """Run the API server."""
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())
