# Multi-stage Dockerfile for ANPR FastAPI application
# Stage 1: Builder (dependencies compilation)
FROM python:3.11-slim AS builder

WORKDIR /build

# Install system build dependencies for compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specification and minimal source for dependency resolution
COPY pyproject.toml README.md /build/
COPY api/ /build/api/
COPY workers/ /build/workers/
COPY db/ /build/db/
COPY anpr_core/ /build/anpr_core/

# Install Python dependencies to a venv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -e .

# Stage 2: Runtime (minimal image)
FROM python:3.11-slim

LABEL org.opencontainers.image.title="ANPR Backend API"
LABEL org.opencontainers.image.description="Automatic Number Plate Recognition FastAPI service"
LABEL org.opencontainers.image.authors="saitarrunpitta@gmail.com"

WORKDIR /app

# Install runtime dependencies only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application source
COPY api/ /app/api/
COPY workers/ /app/workers/
COPY db/ /app/db/
COPY ingest/ /app/ingest/
COPY anpr_core/ /app/anpr_core/
COPY pyproject.toml /app/

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    chown -R appuser:appuser /app

USER appuser

# Set environment
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Health check: liveness probe (lightweight)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# Expose API port
EXPOSE 8000

# Default command: run FastAPI with uvicorn
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
