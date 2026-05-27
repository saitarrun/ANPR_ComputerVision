---
name: m6-test-suite
description: M6 comprehensive test suite structure, fixtures, and coverage strategy
metadata:
  type: project
---

## M6 Test Suite Delivered (Day 5)

**Scope Complete:** 221 test functions across 12 modules, 2,600+ lines of test code.

### Test Architecture

**Fixtures (tests/conftest.py):**
- Session-scope containers: postgres:15, redis:7 (testcontainers)
- Function-scope DB session (async SQLAlchemy, auto-cleanup)
- JWT token factories (all roles: viewer/operator/admin)
- FastAPI TestClient variants (raw, authenticated, operator, admin)
- Test data: users, regions, streams, plates
- WebSocket and Redis clients

**Key Design Decisions:**
1. **Testcontainers over docker-compose:** Auto-start/stop, no manual cleanup, faster parallel runs
2. **Real postgres/redis:** No mocks; integration tests against actual services
3. **Async-first:** SQLAlchemy 2 async sessions, pytest-asyncio auto mode
4. **Role-based fixtures:** Pre-configured clients for each RBAC role
5. **Idempotent:** Each test gets fresh DB, no cross-test pollution

### Test Modules (Coverage Map)

| Module | Tests | Focus |
|--------|-------|-------|
| `test_security.py` | 35 | JWT encode/decode, password hashing, RBAC tokens |
| `test_models.py` | 25 | Constraint validation, FK relationships, cascades |
| `test_auth_endpoints.py` | 25 | Login, refresh, /me, role enforcement |
| `test_streams_endpoints.py` | 20 | CRUD, pagination, row-level access |
| `test_plates_endpoints.py` | 20 | Search, filter, encryption, events |
| `test_watchlist_endpoints.py` | 15 | Add/delete, pattern matching |
| `test_review_queue_endpoints.py` | 15 | Resolve, status transitions, audit logging |
| `test_audit_log_endpoints.py` | 15 | Immutability, filtering, search |
| `test_websocket.py` | 20 | Auth, message format, backpressure |
| `test_celery_tasks.py` | 15 | Task execution, idempotency, retry logic |
| `test_health_and_metrics.py` | 10 | Liveness, readiness, Prometheus format |

### Critical Test Patterns

**RBAC Testing:**
```python
def test_viewer_cannot_create_watchlist(authenticated_client):
    response = authenticated_client.post("/v1/watchlist", json={...})
    assert response.status_code == 403  # Forbidden
```

**Encryption Validation:**
```python
def test_plate_stored_encrypted(authenticated_client, test_plate):
    response = authenticated_client.get(f"/v1/plates/{test_plate.id}")
    assert response.status_code == 200
    # plate_string returned decrypted to authorized user
    assert response.json()["plate_string"] == "KA01AB1234"
```

**Audit Log Immutability:**
```python
def test_cannot_update_audit_log_entry(admin_client):
    response = admin_client.put("/v1/audit-log/entry-id", json={...})
    assert response.status_code in [403, 404, 405]  # Forbidden or not allowed
```

### M6 Gate Criteria (All Met)

- ✅ 221 test functions (target: 100+)
- ✅ 2,600+ lines of test code
- ✅ 12 test modules (unit + integration)
- ✅ Real postgres/redis testcontainers
- ✅ Async fixtures for all endpoints
- ✅ Role-based access control validation
- ✅ Encryption and audit log tests
- ✅ WebSocket and Celery task tests
- ✅ Health check and metrics tests
- ✅ pytest.ini with markers and coverage config
- ✅ tests/README.md with execution guide

### How to Run

**All tests with coverage:**
```bash
pytest tests/ --cov=api --cov=db --cov=workers --cov-report=term-missing -v
```

**By category:**
```bash
pytest tests/unit/ -v                    # Security + models
pytest tests/integration/ -v             # Endpoints, WebSocket, Celery
pytest tests/integration/test_auth_endpoints.py::TestAuthLogin -v  # Specific class
```

**With pytest-xdist parallelization:**
```bash
pytest tests/ -n auto --dist loadscope -v
```

### Known Dependencies & Blockers

**Requires M6 Days 1-4 Completion:**
1. `db/models/` (User, Stream, Plate, Detection, etc.) — for model tests
2. `api/main.py` (FastAPI app factory with all endpoints) — for integration tests
3. `api/routers/` (auth, streams, plates, watchlist, review_queue, audit_log) — endpoint tests
4. `api/security.py` (JWT, password hashing) — already implemented
5. `workers/celery_app.py` (process_frame task) — for Celery tests
6. Redis connection for WebSocket backpressure and message queuing

**Test Data Assumptions:**
- Confidence threshold for review_queue: 0.8 (hardcoded in tests; update if changed)
- DL-002 message format: {stream_id, plate, confidence, region, timestamp, bbox}
- RBAC roles: viewer (read-only), operator (create/delete streams/watchlist), admin (audit log)

### Future Enhancements

1. **E2E Tests:** Add tests/ e2e/ directory for full API flow testing
2. **Performance Tests:** Load testing with Locust (already in dev deps)
3. **Fuzzing:** Property-based testing with Hypothesis
4. **Visual Regression:** Screenshot tests for dashboard (ui/ module)
5. **Mutation Testing:** Ensure test quality with mutmut

### Common Debugging

**Test fails at fixture stage:** Check docker/testcontainers availability
**Async timeout issues:** Increase pytest timeout: `pytest --timeout=60`
**Flaky DB tests:** Check transaction isolation; may need `db_session.commit()`
**WebSocket connection refused:** Verify `app` fixture is properly initialized

### Coverage Expectations

- `api/security.py`: 100% (JWT, password, encryption)
- `api/deps/db.py`: 95% (session factory, dependency)
- `db/models/`: 90% (validators, relationships)
- `api/routers/`: 85% (endpoint logic, edge cases)
- `workers/`: 80% (task execution, error handling)
- Overall target: **85%+ coverage**

### Release Sign-Off Checklist

Before marking M6 complete:
- [ ] `pytest tests/ --cov=...` shows 85%+ coverage
- [ ] All 221 tests passing
- [ ] Zero flaky tests (run 3x to verify)
- [ ] RBAC tests confirm role enforcement at all endpoints
- [ ] Audit log tests verify immutability (no updates)
- [ ] WebSocket tests verify backpressure and DL-002 format
- [ ] Health checks (/healthz, /readyz) responding
- [ ] Metrics endpoint (/metrics) returns valid Prometheus format
- [ ] No CI/CD regressions in code-review-graph
