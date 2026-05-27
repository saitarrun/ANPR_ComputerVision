---
name: decision-log-m6
description: Decision log DL-001 through DL-005 covering all M6 backend architecture decisions — DB schema, WebSocket format, Docker Compose, ML-API coupling, test bar
metadata:
  type: project
---

## Decision Log — M6 Backend Implementation

Sprint start: 2026-05-27
Sprint end: 2026-05-31 (5 days)
Critical gate: M6 completion unblocks M7–M11 (14 days downstream)

---

### DL-001 — DB Schema Canonical Set

**Date:** 2026-05-27
**Asked by:** User (broadcast request)
**User answer:** Merge into 9 tables — regions, cameras, plates, detections, users, audit_log, watchlist, review_queue, api_keys
**Decision:** 9 tables are the canonical M6 schema. Prior 6-table memory (anpr_db_schema.md) was phase-0 scoped; it now includes watchlist, review_queue, and api_keys as first-class M6 tables.
**Alembic migration file:** `db/migrations/versions/001_init_schema.py`
**Impacted agents:** backend-engineer, database-engineer, security-threat-architect
**Follow-up tasks:**
- database-engineer: Author `001_init_schema.py` with all 9 tables, constraints, indexes
- backend-engineer: SQLAlchemy models for all 9 tables
- security-threat-architect: Verify encryption coverage on watchlist.plate_pattern + api_keys.key_hash

---

### DL-002 — WebSocket Payload Format

**Date:** 2026-05-27
**Asked by:** User (broadcast request)
**User answer:** Metadata-only (no JPEG frames in WebSocket)
**Payload format:**
```json
{
  "stream_id": "<uuid>",
  "timestamp_ms": 1716800000000,
  "frames": [
    {
      "detections": [
        { "bbox": [x1, y1, x2, y2], "plate": "<str>", "confidence": 0.95, "region": "IN" }
      ],
      "fps": 12.4,
      "queue_depth": 3
    }
  ]
}
```
**Video stream:** MJPEG or HLS — deferred to M7+ optimization
**Impacted agents:** frontend-engineer-agent, backend-engineer, ml-engineer
**Follow-up tasks:**
- backend-engineer: Implement `/ws/stream/{stream_id}` emitting this exact schema; no image_b64 field
- frontend-engineer-agent: React WebSocket consumer reads this schema; does NOT expect image_b64_jpeg in WS messages; sources video via separate MJPEG endpoint
- ml-engineer: Celery task output must serialize to this schema before Redis pub; no raw frame bytes in message bus

---

### DL-003 — Docker Compose Infrastructure

**Date:** 2026-05-27
**Asked by:** User (broadcast request)
**User answer:** Add api + worker services to existing compose stack
**Full M6 compose services:** postgres, redis, minio, prometheus, grafana, api (FastAPI), worker (Celery)
**Host:** OrbStack (not Docker Desktop)
**`docker compose up` brings full M6 stack**
**Impacted agents:** devops-architect, backend-engineer
**Follow-up tasks:**
- devops-architect: Add `api` and `worker` service definitions to docker-compose.yml; confirm health-check dependencies (api depends_on postgres+redis, worker depends_on redis+postgres)
- backend-engineer: Ensure FastAPI app reads config from env vars (DATABASE_URL, REDIS_URL, MINIO_ENDPOINT, etc.) so it runs identically in compose and bare-metal

---

### DL-004 — ML-API Coupling Model

**Date:** 2026-05-27
**Asked by:** User (broadcast request)
**User answer:** Celery + Redis — full async, no in-process blocking
**Architecture:** Celery task consumes from ingest queue → runs ML pipeline → writes results to DB → publishes to Redis channel → FastAPI WebSocket fan-out
**Redis broker:** yes (same Redis instance as rate-limiting)
**Impacted agents:** ml-engineer, backend-engineer
**Follow-up tasks:**
- ml-engineer: Package ML inference pipeline as Celery task; task signature: `process_frame(stream_id, frame_bytes_b64, camera_id) -> DetectionResult`; publish result to Redis channel `detections:{stream_id}`
- backend-engineer: FastAPI WebSocket endpoint subscribes to `detections:{stream_id}` via Redis pub/sub; fan-out to all connected clients for that stream_id; no ML code in API process

---

### DL-005 — M6 Test Bar

**Date:** 2026-05-27
**Asked by:** User (broadcast request)
**User answer:** Integration tests using testcontainers or real compose stack; 100+ tests total
**Gate criteria:**
- All 14 REST endpoints tested (auth required paths, RBAC enforcement)
- WebSocket endpoint tested (connection, message schema validation, fan-out)
- RBAC: viewer/operator/admin role matrix tested explicitly
- Celery tasks tested end-to-end (task enqueue → DB write → Redis publish)
- Fernet encryption: plate_string stored encrypted, decrypted correctly on read
- Audit log: append-only constraint tested (no UPDATE/DELETE succeeds)
- 100+ test count (integration + unit combined)
**Impacted agents:** qa-test-engineer, backend-engineer
**Follow-up tasks:**
- qa-test-engineer: Own test suite scaffolding; testcontainers preferred for CI portability; test all 14 endpoints + WS + RBAC matrix + Celery + encryption + audit immutability
- backend-engineer: Expose test fixtures (db session, auth tokens per role, mock Celery worker) via conftest.py

---

## Sprint Execution Plan

| Day | Owner | Deliverable |
|-----|-------|-------------|
| 1   | database-engineer + backend-engineer | SQLAlchemy models + Alembic 001_init_schema.py |
| 2   | backend-engineer + security-threat-architect | JWT auth + RBAC middleware + Fernet encryption |
| 3   | backend-engineer | All 14 REST endpoints wired |
| 4   | backend-engineer + ml-engineer | WebSocket + Celery tasks + watchlist alert logic |
| 5   | backend-engineer + qa-test-engineer | Audit log + health endpoints + 100+ tests + verification |

**Frontend unblock:** React SPA (25-day parallel track) starts after `/openapi.json` is live (end of Day 3).

**Why:** [[backend-m6-scope]] [[anpr-db-schema]]
