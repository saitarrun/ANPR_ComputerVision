# M6 Test Suite

Comprehensive test suite for the ANPR backend (100+ tests, 85%+ coverage).

## Quick Start

### Prerequisites
- Python 3.11+
- Docker (for testcontainers)
- PostgreSQL 15 and Redis 7 (via testcontainers)

### Install Test Dependencies
```bash
pip install -e ".[dev]"
```

### Run All Tests
```bash
pytest tests/ -v --tb=short
```

### Run Tests by Category
```bash
# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# With coverage report
pytest tests/ --cov=api --cov=db --cov=workers --cov-report=html --cov-report=term-missing
```

## Test Structure

### Unit Tests (`tests/unit/`)

#### `test_security.py` (20 tests)
- JWT encode/decode round-trip
- JWT expiry and signature validation
- Password hashing and verification
- Fernet encryption/decryption
- RBAC role validation
- Token type validation (access vs refresh)

#### `test_models.py` (15 tests)
- User model: email uniqueness, role validation
- Region model: code uniqueness
- Stream model: foreign keys, cascades
- Plate model: confidence bounds, encryption requirement
- Detection model: plate/stream relationships
- Audit log model: append-only semantics
- Watchlist model: required fields
- Review queue model: status validation

### Integration Tests (`tests/integration/`)

#### `test_auth_endpoints.py` (25 tests)
- `POST /v1/auth/login`: valid/invalid credentials
- `POST /v1/auth/refresh`: token refresh
- `GET /v1/auth/me`: current user info
- RBAC enforcement: viewer/operator/admin roles

#### `test_streams_endpoints.py` (20 tests)
- `GET /v1/streams`: list, pagination, row-level access
- `POST /v1/streams`: create (operator+)
- `GET /v1/streams/{id}`: detail + stats
- `DELETE /v1/streams/{id}`: remove (operator+)

#### `test_plates_endpoints.py` (20 tests)
- `GET /v1/plates`: list, search, filter by region/date
- `GET /v1/plates/{id}`: detail
- `GET /v1/plates/{id}/events`: detection history
- Encryption validation: plate_string stored encrypted

#### `test_watchlist_endpoints.py` (15 tests)
- `POST /v1/watchlist`: add entry (operator+)
- `GET /v1/watchlist`: list entries
- `DELETE /v1/watchlist/{id}`: remove entry
- Pattern matching: exact and wildcard

#### `test_review_queue_endpoints.py` (15 tests)
- `GET /v1/review-queue`: list pending (operator+)
- `POST /v1/review-queue/{id}/resolve`: mark reviewed
- Status transitions: pending → approved/rejected/flagged
- Audit log creation on resolve

#### `test_audit_log_endpoints.py` (15 tests)
- `GET /v1/audit-log`: list entries (admin only)
- Filtering: by action, user_id, date range
- Immutability: cannot UPDATE/DELETE
- Audit log creation on mutations

#### `test_websocket.py` (20 tests)
- `WS /v1/stream/{id}`: auth, message reception
- Message format validation (DL-002)
- Multiple clients, backpressure (buffer size 30)
- Client disconnection cleanup

#### `test_celery_tasks.py` (15 tests)
- `process_frame` task: high/low confidence handling
- Detection and plate record creation
- Redis publishing (DL-002 format)
- Review queue creation on low confidence
- Idempotency: same frame → single entry
- Retry logic and error handling
- Task status polling

#### `test_health_and_metrics.py` (10 tests)
- `GET /healthz`: liveness (always 200)
- `GET /readyz`: readiness (postgres/redis checks)
- `GET /metrics`: Prometheus metrics format
- `GET /openapi.json`: OpenAPI schema validation
- `/docs` and `/redoc` availability

## Test Infrastructure

### Fixtures (`tests/conftest.py`)

#### Containers (Session Scope)
- `postgres_container`: PostgreSQL 15 testcontainer
- `redis_container`: Redis 7 testcontainer
- `postgres_url`: Async connection string
- `redis_url`: Redis connection string

#### Database (Function Scope)
- `db_engine`: Async SQLAlchemy engine
- `db_session`: Fresh session per test
- `db_session_sync`: Sync wrapper

#### Authentication
- `jwt_secret`: Test JWT secret
- `auth_token_factory`: Create tokens for any role/user
- `refresh_token_factory`: Create refresh tokens

#### FastAPI Clients
- `client`: Raw TestClient
- `authenticated_client`: With viewer token + header
- `operator_client`: With operator token + header
- `admin_client`: With admin token + header

#### Test Data
- `test_user`: Viewer user in DB
- `operator_user`: Operator user in DB
- `admin_user`: Admin user in DB
- `test_region`: India region
- `test_stream`: Test RTSP stream
- `test_plate`: Test plate record
- `redis_client`: Redis connection

#### Utilities
- `assert_status`: Helper to assert HTTP status
- `assert_schema`: Helper to validate response keys
- `websocket_url`: WebSocket URL with auth

## Running Tests

### All Tests with Coverage
```bash
pytest tests/ \
  --cov=api \
  --cov=db \
  --cov=workers \
  --cov-report=term-missing \
  --cov-report=html \
  -v
```

### Tests by Marker
```bash
pytest tests/ -m unit          # Unit tests
pytest tests/ -m integration   # Integration tests
pytest tests/ -m slow          # Slow tests (>1s)
pytest tests/ -m "not slow"    # Exclude slow tests
```

### Parallel Execution
```bash
pytest tests/ -n auto --dist loadscope
```

### Verbose with Full Tracebacks
```bash
pytest tests/ -vv --tb=long
```

## Test Coverage Targets

**M6 Gate Criteria:**
- **Tests Collected:** 115+
- **Tests Passed:** 115+
- **Coverage:** 85%+ (lines)
- **Failed:** 0
- **Errors:** 0
- **Flaky Tests:** 0 (must investigate and fix)

## Environment Setup

### For Local Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run pytest with auto-discovery
pytest tests/ --tb=short -v

# Run with testcontainers (docker must be running)
# Testcontainers will auto-start postgres and redis
```

### Docker Compose Stack (Alternative)

If testcontainers fails, use docker-compose:

```bash
docker-compose -f ops/docker-compose.test.yml up -d postgres redis
export TEST_POSTGRES_URL="postgresql+asyncpg://user:password@localhost/anpr_test"
export TEST_REDIS_URL="redis://localhost:6379/0"
pytest tests/ -v
```

## CI/CD Integration

### GitHub Actions Example
```yaml
- name: Run tests
  run: |
    pytest tests/ \
      --cov=api --cov=db --cov=workers \
      --cov-report=xml \
      --junit-xml=test-results.xml \
      -v
```

## Known Issues & Gotchas

### 1. Testcontainers Startup Delay
- First test run takes 10-15s to start containers
- Containers are cached across runs
- Clear cache: `rm -rf ~/.testcontainers`

### 2. Async Test Ordering
- Tests are executed serially to avoid race conditions
- Use `pytest-asyncio` for async support

### 3. Database Isolation
- Each test gets a fresh session
- Tables are created/dropped per test
- No cross-test pollution

### 4. WebSocket Tests
- WebSocket tests may fail if FastAPI app not properly initialized
- Use `client.websocket_connect()` within test context

## Extending Tests

### Adding a New Test
1. Create `test_*.py` in appropriate directory (unit or integration)
2. Use fixtures from `conftest.py`
3. Name test function starting with `test_`
4. Add marker: `@pytest.mark.integration` or `@pytest.mark.unit`

### Example Integration Test
```python
@pytest.mark.integration
def test_example(self, authenticated_client, test_stream):
    """Test that demonstrates fixture usage."""
    response = authenticated_client.get(f"/v1/streams/{test_stream.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_stream.id
```

### Example Unit Test
```python
def test_jwt_encode_decode(jwt_secret: str):
    """Test JWT round-trip."""
    from api.security import encode_jwt, decode_jwt
    token = encode_jwt("user-1", "viewer", jwt_secret)
    payload = decode_jwt(token, secret=jwt_secret)
    assert payload["user_id"] == "user-1"
```

## Debugging Tests

### Verbose Output
```bash
pytest tests/integration/test_auth_endpoints.py::TestAuthLogin::test_login_valid_credentials -vv
```

### Print Debug Info
```python
def test_example(authenticated_client):
    response = authenticated_client.get("/v1/auth/me")
    print(response.json())  # Will print in pytest -s
    assert response.status_code == 200
```

### Drop into Debugger
```python
import pdb; pdb.set_trace()
```

### Use pytest --pdb
```bash
pytest tests/ --pdb  # Drops into debugger on failure
```

## Performance Notes

- **Unit tests**: <50ms each
- **Integration tests**: 100-500ms each (DB/network I/O)
- **Total suite**: ~30-60 seconds (sequential)
- **Parallel**: ~10-15 seconds (with pytest-xdist)

## Release Checklist

Before M6 sign-off:
- [ ] All 115+ tests passing
- [ ] 85%+ code coverage
- [ ] Zero flaky tests
- [ ] All security tests pass
- [ ] RBAC tests confirm role enforcement
- [ ] Audit log tests verify immutability
- [ ] Health checks responding
- [ ] Metrics endpoint working
