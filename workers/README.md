# Celery Workers: ML Pipeline Task Queue

Industrial-grade task queue for ANPR frame processing, watchlist checking, and data cleanup.

## Overview

The `workers/` module provides Celery tasks that bridge the ingest pipeline (webcam, RTSP, iPhone) to the ML inference chain (YOLO → OCR → region classification) and downstream persistence (PostgreSQL, Redis, S3).

### Architecture

```
Ingest Pipeline (webcam/RTSP/file)
         ↓
    Base64 frame bytes
         ↓
    Celery queue (Redis broker)
         ↓
    process_frame task
         ├─ Decode frame
         ├─ YOLO detection
         ├─ OCR fusion (Paddle + CRNN)
         ├─ Region classification
         ├─ Quality gate
         └─ On success: write DB + publish Redis
         └─ On failure: routing to review_queue
```

## Tasks

### `process_frame` — Main ML Pipeline Task

**Signature:**
```python
process_frame(
    stream_id: str,         # UUID of ingestion stream
    frame_bytes_b64: str,   # Base64-encoded JPEG/PNG
    camera_id: int,         # Foreign key to cameras table
    db: Database | None,    # Database dependency (injected)
    redis_client: ...,      # Redis client (injected)
    confidence_threshold: float = 0.75,
) -> dict
```

**Returns:**
```json
{
  "success": true,
  "plate": "ABC123",
  "confidence": 0.92,
  "region": "IN",
  "detection_id": 12345,
  "review_queue_id": null,
  "error": null
}
```

**Behavior:**

| Scenario | Action |
|---|---|
| Frame decode fails | Return `success=False`, `error="frame_decode_failed"` |
| No plates detected | Return `success=False`, `error="no_detections"` |
| OCR returns empty text | Return `success=False`, `error="no_valid_ocr"` |
| Region classification fails | Return `success=False`, `error="no_valid_ocr"` |
| Confidence < threshold | Return `success=False`, `error="confidence_threshold_not_met"` + write to `review_queue` table |
| Success (confidence ≥ threshold) | Write to `plates` + `detections` tables, publish to Redis `detections:{stream_id}` channel in DL-002 format |

**Idempotency:**

Tasks are idempotent via frame hash (`MD5(frame_bytes)[:8]`). On retry, the same frame will deterministically produce the same result. Database writes use `INSERT ... ON CONFLICT UPDATE` semantics (plates table has unique constraint on `(plate_string, region_id)`).

**Retry Logic:**

- Max retries: 3
- Base delay: 5 seconds
- Exponential backoff: `5 * (attempt + 1)`
- Retry conditions: transient errors (DB timeout, OOM, Redis unavailable)
- Non-transient failures (bad input, model inference failure): logged but not retried

**Performance Targets:**

- Latency: <500ms per frame (on GPU)
- Memory: ~2GB per worker (YOLO + OCR models loaded)
- Throughput: 20+ frames/sec per worker
- Concurrency: 4 workers × 5 concurrent tasks = 20 parallel pipelines

### `check_watchlist_match` — Alerting Task

Async watchlist matching (triggered by `process_frame` on success).

**Signature:**
```python
check_watchlist_match(
    plate: str,
    region: str,
    detection_id: int,
) -> dict
```

**Returns:**
```json
{
  "matched": true,
  "alert_ids": [1, 2, 3],
  "error": null
}
```

### `purge_expired_records` — Scheduled Cleanup

Delete detections and plates older than retention window (default: 30 days).

**Schedule:** Nightly @ 2 AM UTC

**Signature:**
```python
purge_expired_records(retention_days: int = 30) -> dict
```

**Returns:**
```json
{
  "deleted_detections": 45000,
  "deleted_plates": 120,
  "error": null
}
```

### `archive_audit_logs` — Scheduled Archival

Archive audit logs older than 90 days to S3, then delete.

**Schedule:** Weekly @ 3 AM UTC (Sunday)

**Signature:**
```python
archive_audit_logs(archive_days: int = 90) -> dict
```

**Returns:**
```json
{
  "archived_records": 250000,
  "s3_key": "s3://anpr-audit/archive/2026-05-27.tar.gz",
  "error": null
}
```

## Integration with FastAPI

### Initialization

```python
# api/main.py
from fastapi import FastAPI
from workers.tasks import make_celery, set_celery_app
from db.core import Database
import os

app = FastAPI()

# Initialize Celery
celery_app = make_celery(
    broker_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    result_backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)
set_celery_app(celery_app)

# Initialize Database
database = Database(os.getenv("DATABASE_URL"))

@app.on_event("startup")
async def startup():
    # Verify Celery and DB connectivity
    # celery_app.backend.get_state("test-task-id")
    # database.health_check()
    pass

@app.on_event("shutdown")
async def shutdown():
    await database.close()
```

### Enqueuing Tasks from API Endpoint

```python
# api/routers/ingest.py
from fastapi import APIRouter, Depends, HTTPException
from workers.tasks import process_frame
import base64

router = APIRouter()

@router.post("/api/v1/ingest/frame")
async def ingest_frame(
    stream_id: str,
    frame_bytes: bytes,  # or base64-encoded
    camera_id: int,
    dependencies: ...,
):
    """Enqueue frame for processing."""
    
    frame_b64 = base64.b64encode(frame_bytes).decode("utf-8")
    
    # Fire-and-forget
    task = process_frame.apply_async(
        args=(stream_id, frame_b64, camera_id),
        task_id=f"{stream_id}_{hashlib.md5(frame_bytes).hexdigest()[:8]}",
    )
    
    return {
        "task_id": task.id,
        "status": "queued",
    }

@router.get("/api/v1/ingest/task/{task_id}")
async def get_task_status(task_id: str):
    """Poll task result."""
    task_result = process_frame.AsyncResult(task_id)
    
    return {
        "task_id": task_id,
        "status": task_result.status,
        "result": task_result.result if task_result.ready() else None,
    }
```

## Deployment

### Development (Single Worker)

```bash
# Terminal 1: Redis
make up  # Starts redis:6379

# Terminal 2: Celery worker
celery -A workers.tasks worker --loglevel=info --concurrency=2

# Terminal 3: FastAPI
uvicorn api.main:app --reload --port 8000
```

### Production (Multi-Worker)

```bash
# Docker Compose (in ops/docker-compose.yml)
services:
  celery-worker-1:
    build: .
    command: celery -A workers.tasks worker --loglevel=info --concurrency=5
    environment:
      - REDIS_URL=redis://redis:6379/0
      - DATABASE_URL=postgresql+psycopg://...
    depends_on:
      - redis
      - postgres

  celery-worker-2:
    # ... same as worker-1 (horizontal scaling)

  celery-beat:
    # Scheduler for purge_expired_records, archive_audit_logs
    build: .
    command: celery -A workers.tasks beat --loglevel=info
    environment:
      - REDIS_URL=redis://redis:6379/0
      - DATABASE_URL=postgresql+psycopg://...
    depends_on:
      - redis
```

### Monitoring

#### Celery Flower (Web UI)

```bash
pip install flower
flower -A workers.tasks --port=5555
# Visit http://localhost:5555
```

#### Prometheus Metrics

```python
# api/metrics.py
from prometheus_client import Counter, Histogram

task_duration_seconds = Histogram(
    "celery_task_duration_seconds",
    "Task execution time",
    ["task_name", "status"],
)

task_count = Counter(
    "celery_task_count_total",
    "Task execution count",
    ["task_name", "status"],
)

# In task:
task_duration_seconds.labels(
    task_name="process_frame",
    status="success"
).observe(elapsed_time)
```

#### Logging

All tasks use Python's standard `logging` module with structured log lines:

```python
logger.info(f"[{task_id}] Processing frame ... region={region}")
# Output: 2026-05-30 14:23:45 [abc123def] Processing frame ... region=IN
```

Configure in `logging.yaml` or environment:

```bash
export LOG_LEVEL=DEBUG  # or INFO, WARNING
```

## Testing

### Unit Tests (Mocked)

```bash
pytest tests/unit/test_tasks.py -v
```

### Integration Tests (Real Redis, Mocked ML)

```bash
pytest tests/integration/test_celery_pipeline.py -v
```

Requires:
- Redis running on `localhost:6379` (DB 1 for tests)
- OpenCV + NumPy

### Load Test

```bash
locust -f benchmarks/celery_load.py --host=http://localhost:8000
```

## Configuration

Environment variables in `.env`:

```bash
# Celery
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=${REDIS_URL}
CELERY_RESULT_BACKEND=${REDIS_URL}

# ML Pipeline
CONFIDENCE_PLATE=0.75
CONFIDENCE_CHAR=0.60

# Task Retry
CELERY_TASK_MAX_RETRIES=3
CELERY_TASK_DEFAULT_RETRY_DELAY=5

# Cleanup (schedule)
PURGE_RETENTION_DAYS=30
ARCHIVE_RETENTION_DAYS=90
```

## Troubleshooting

### Worker Not Picking Up Tasks

```bash
# Check Celery app is initialized
celery -A workers.tasks inspect active

# Check Redis connectivity
redis-cli PING  # Should return "PONG"

# Check task routing
celery -A workers.tasks inspect registered
```

### Task Timeout

**Symptom:** `Celery.Task.FAILURE: Task timed out`

**Root Cause:** Long-running inference (GPU swap, model load on cold start)

**Fix:**
- Increase task timeout: `@task(time_limit=600)`
- Warm up GPU between tasks
- Pre-load models in worker startup

### Database Connection Pool Exhaustion

**Symptom:** `QueuePool limit exceeded`

**Root Cause:** Tasks holding DB connections

**Fix:**
- Use `NullPool` for serverless (✓ already in `db/core.py`)
- Limit task concurrency: `--concurrency=4`
- Reduce transaction scope (commit early)

### Redis Memory Pressure

**Symptom:** `redis.exceptions.ResponseError: OOM command not allowed`

**Root Cause:** Result backend accumulating completed tasks

**Fix:**
- Set result TTL: `@task(result_expires=3600)` (1 hour)
- Reduce max-retries
- Monitor Redis `INFO memory`

## References

- [Celery Documentation](https://docs.celeryproject.org)
- [Celery Best Practices](https://docs.celeryproject.org/en/stable/userguide/tasks.html#tips-and-best-practices)
- [DL-002 Redis Message Format](../docs/FORMATS.md)
- [Database Schema](../db/models/__init__.py)
- [ML Pipeline](../anpr_core/README.md)
