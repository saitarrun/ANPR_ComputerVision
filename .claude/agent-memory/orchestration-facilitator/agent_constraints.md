---
name: agent-constraints
description: Known per-agent constraints and coordination patterns observed in the ANPR project
metadata:
  type: project
---

## Agent Constraints — ANPR Project

Observed as of 2026-05-27 (M6 sprint start).

### backend-engineer
- Central dependency for M6; all other agents wait on their deliverables
- Owns conftest.py fixtures that qa-test-engineer depends on
- Must expose `/openapi.json` before frontend-engineer-agent can begin React SPA work

### database-engineer
- Schema migrations require careful ordering: all 9 tables in a single `001_init_schema.py` (not split across files) to avoid FK dependency ordering bugs
- EXPLAIN ANALYZE required on typical queries before sign-off (per anpr_db_schema.md acceptance criteria)

### security-threat-architect
- Must review: Fernet key rotation plan, api_keys.key_hash algorithm choice (bcrypt recommended), audit_log DB-level ACL enforcement
- Non-negotiables: no plaintext plate_string in DB, no secrets hardcoded, RBAC at both endpoint + row level

### devops-architect
- OrbStack confirmed (not Docker Desktop) — no Docker Desktop-specific flags or volumes
- Compose health-check dependency order: api must wait on postgres + redis readiness probes, not just container start

### ml-engineer
- Celery task interface is the API contract with backend-engineer: `process_frame(stream_id, frame_bytes_b64, camera_id) -> DetectionResult`
- NO raw frame bytes in Redis messages — serialize to DL-002 payload format before publishing
- Latency budget for Celery task: <200ms total inference (per ml_engineering_decisions.md)

### frontend-engineer-agent
- WebSocket consumer must NOT expect image_b64_jpeg (DL-002); video sourced separately via MJPEG endpoint
- React SPA start is gated on `/openapi.json` going live (end of M6 Day 3)
- TanStack Query + WebSocket architecture confirmed (per frontend_architecture.md)

### qa-test-engineer
- testcontainers preferred for CI portability (real DB, not mocks)
- 100+ test minimum is a hard gate — not a soft target
- Must cover: 14 endpoints, WS, RBAC matrix, Celery, Fernet, audit immutability

### integration-cleanup-engineer
- Activated post-M6 to resolve any cross-agent integration seams before M7 begins
- Watches for: contract drift between ml-engineer Celery output and backend-engineer WS consumer
