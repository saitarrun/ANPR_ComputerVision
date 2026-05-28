# ANPR End-to-End Demo

Full pipeline demonstration: webcam/file → API ingest → Celery ML → DB persistence → WebSocket streaming.

## Setup

### Start Services

```bash
# Ensure OrbStack is running
open /Applications/OrbStack.app

# Start all services (postgres, redis, minio, prometheus, grafana, api, worker)
docker-compose up --remove-orphans
```

Check health:
```bash
curl http://localhost:8000/healthz    # Should return {"status":"ok"}
curl http://localhost:8000/readyz     # Should return {"status":"ready"}
```

### Initialize Database

Run Alembic migrations (if not auto-run on API startup):
```bash
docker-compose exec api alembic upgrade head
```

### Create Demo User

```bash
# Use psql to insert a demo user (or call /v1/auth/register if implemented)
docker-compose exec postgres psql -U anpr -d anpr_db -c \
  "INSERT INTO users (id, email, hashed_password, role) VALUES ('demo-user', 'demo@example.com', 'hashed', 'viewer');"
```

Or use API to create/login (when auth endpoints are fully implemented).

## Run Demo

### Option 1: Webcam Demo

```bash
python demo.py --source webcam \
  --stream-id demo-stream \
  --camera-id demo-camera-1 \
  --email demo@example.com \
  --password demo123
```

Detections appear in real-time via WebSocket.

### Option 2: File Demo

```bash
python demo.py --source file \
  --file /path/to/video.mp4 \
  --stream-id demo-stream \
  --camera-id demo-camera-1 \
  --max-frames 100
```

### Option 3: CLI Ingest (without WebSocket)

```bash
python ingest_cli.py --source webcam \
  --stream-id demo-stream \
  --camera-id demo-camera-1 \
  --api-url http://localhost:8000 \
  --token <JWT_TOKEN>
```

Frames are queued to Celery. Results in PostgreSQL + Redis.

## Expected Flow

1. **Ingest**: Frame sent to `POST /v1/ingest/frame`
2. **Queue**: Task enqueued to Celery (Redis broker)
3. **Process**: `process_frame` task runs ML pipeline (YOLO → OCR → region → quality gate)
4. **Persist**: Results written to PostgreSQL (plates, detections tables)
5. **Publish**: Detection result published to Redis channel `detections:{stream_id}`
6. **Stream**: WebSocket client (connected to `WS /v1/stream/{stream_id}`) receives message in real-time

## Monitoring

### API Docs
```
http://localhost:8000/docs     # Swagger UI
http://localhost:8000/redoc    # ReDoc
http://localhost:8000/openapi.json  # OpenAPI schema
```

### Metrics
```
http://localhost:8000/metrics   # Prometheus metrics
http://localhost:9090           # Prometheus UI
http://localhost:3000           # Grafana (optional)
```

### Database
```bash
docker-compose exec postgres psql -U anpr -d anpr_db
\d  # List tables
SELECT * FROM plates LIMIT 5;
SELECT * FROM detections LIMIT 5;
```

### Redis
```bash
docker-compose exec redis redis-cli
SUBSCRIBE detections:*   # Watch all detection messages
```

## Troubleshooting

### Services not starting
```bash
docker-compose logs
docker-compose ps  # Check health status
```

### API not responding
```bash
curl -v http://localhost:8000/healthz
docker-compose logs api
```

### Celery task not executing
```bash
docker-compose logs worker
docker-compose exec redis redis-cli KEYS "celery*"  # Check task queue
```

### WebSocket connection refused
- Verify `token` parameter or `Authorization` header
- Check WebSocket logs: `docker-compose logs api`
- Try: `wscat -c "ws://localhost:8000/v1/stream/demo-stream?token=<JWT>"`

## Architecture

```
Ingest Source (webcam/file/RTSP/iPhone)
    ↓
API Ingest Endpoint (POST /v1/ingest/frame)
    ↓
Celery Queue (Redis broker)
    ↓
Worker Process (process_frame task)
    ├→ YOLO Detector
    ├→ OCR Fusion (Paddle + CRNN)
    ├→ Region Classifier
    └→ Quality Gate
    ↓
Database Write (PostgreSQL)
    ├→ plates table (encrypted strings)
    └→ detections table (confidence scores)
    ↓
Redis Publish (detections:{stream_id} channel)
    ↓
WebSocket Broadcast (all connected clients)
    ↓
Frontend (React dashboard) [TBD M6-parallel]
```

## Next Steps

- [ ] Implement user registration + authentication endpoints
- [ ] Add more CRUD endpoints (streams, watchlist, review queue, audit log)
- [ ] Build React dashboard (frontend parallel track)
- [ ] Implement WebSocket message filtering (by role/stream)
- [ ] Add rate limiting + API key auth
- [ ] Deploy to production (K8s / cloud platform)
