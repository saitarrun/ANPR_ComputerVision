"""FastAPI application factory and middleware setup."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    # Startup
    yield
    # Shutdown


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="ANPR API",
        description="Industrial-grade Automatic Number Plate Recognition API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Dev: allow all; prod: restrict to frontend domain
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check endpoints (no dependencies required)
    @app.get("/healthz", tags=["health"])
    async def healthz():
        """Liveness probe: service is running."""
        return JSONResponse({"status": "ok"}, status_code=200)

    @app.get("/readyz", tags=["health"])
    async def readyz():
        """Readiness probe: service is ready to handle requests."""
        return JSONResponse({"status": "ready"}, status_code=200)

    @app.get("/metrics", tags=["metrics"])
    async def metrics():
        """Prometheus metrics endpoint (stub for now)."""
        return "# HELP anpr_requests_total Total requests\n# TYPE anpr_requests_total counter\n"

    return app


# Application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.anpr_env == "dev",
        workers=settings.api_workers,
    )
