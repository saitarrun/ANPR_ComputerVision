---
name: threat-model-m6-backend
description: Full security threat model for FastAPI ANPR backend (M6), including assets, boundaries, risks, and controls
metadata:
  type: project
---

## Threat Model: ANPR FastAPI Backend (M6)

### Assets at Risk
1. **User Credentials** — Email, password hash, JWT tokens, refresh tokens
2. **License Plate Data** — Sensitive PII in `plate_string` and detection results
3. **Video Frames & Crops** — S3-stored detection crops and raw frames
4. **API Keys** — S3/MinIO access keys, Celery broker credentials, Redis access
5. **Audit Logs** — Legally-required audit trail in S3 and PostgreSQL
6. **Inference Models** — YOLOv8 and OCR weights (availability/integrity)

### Trust Boundaries
- **Authenticated vs. Unauthenticated**: HTTP endpoints require JWT; WebSocket endpoint optionally accepts token as query param (weak)
- **Client to API**: TLS enforced (assumed in production); secrets in Authorization header (standard)
- **API to Database**: AsyncPg connection pool with bare credentials in URL; no encryption in transit (unsafe if unencrypted DB network)
- **API to S3/MinIO**: Access keys embedded in config; no credential rotation mechanism
- **Celery to Worker**: Redis pubsub with no auth by default; task payloads include user_id and frame data unencrypted

### Attack Surface
1. **Login Endpoint** (`POST /v1/auth/login`) — Password verification, token generation
2. **Data Query Endpoints** (`GET /v1/regions`, `/v1/detections`, `/v1/plates`, etc.) — No per-resource authorization checks
3. **Frame Ingest** (`POST /v1/ingest/frame`) — Base64 decoding, Celery task queueing
4. **WebSocket** (`/v1/stream/{stream_id}`) — Token in query param + logging; potential token replay
5. **CORS Configuration** — Wildcard `*` origin + `allow_credentials=true` (contradictory)
6. **Settings/Config Router** — Likely exposes system state; hardcoded secrets in logs

### Key Vulnerability Classes
- **Authentication Weaknesses**: Weak token validation, WebSocket token in query param, no token blacklist/revocation
- **Authorization Bypass**: No resource-level checks; authenticated users can access all detections/regions/plates
- **Injection**: String-based UUID filters may bypass ORM validation if not strictly typed
- **Information Disclosure**: Error messages leak stack traces; logging doesn't sanitize sensitive data
- **Credential Exposure**: Secrets in environment config, no encryption at rest, logs may capture tokens
- **CORS Misconfiguration**: `*` + credentials = XSS vector for token theft

---

## Identified Risks (Prioritized by Severity)

### CRITICAL

#### **1. CORS Misconfiguration with Credentials (CWE-639, CWE-346)**
**Severity: CRITICAL | Exploitability: 5/5 | Impact: 5/5 | Risk Score: 25**

**Location**: `/Users/saitarrunpitta/Projects/ComputerVision Project/api/main.py`, lines 48-54

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
    allow_credentials=True,  # ← DANGEROUS with wildcard origin
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Attack Vector**:
- Attacker hosts malicious website attacker.com
- Victim visits attacker.com while logged into ANPR UI (any origin, including localhost:3000)
- JavaScript reads Authorization header and sends it to attacker's server
- Attacker gains JWT access token valid for 60 minutes

**Mitigation**:
1. **Remove wildcard origin**: Explicitly whitelist only trusted origins (localhost for dev, specific domain for prod)
2. **Disable `allow_credentials` if `*` used**: Choose one:
   - Either `allow_origins=["*"]` + `allow_credentials=False` (public API, no auth needed)
   - Or `allow_origins=["https://trusted.example.com"]` + `allow_credentials=True` (private API, auth required)
3. **Implement in main.py**:
```python
origins = settings.cors_allowed_origins or ["http://localhost:3000"]  # Explicit list
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],  # Explicit methods, no wildcard
    allow_headers=["authorization", "content-type"],  # Explicit headers
    max_age=600,  # Cache preflight for 10min
)
```

---

#### **2. Missing Resource Authorization Checks (CWE-284, CWE-639)**
**Severity: CRITICAL | Exploitability: 5/5 | Impact: 5/5 | Risk Score: 25**

**Location**: `/Users/saitarrunpitta/Projects/ComputerVision Project/api/routers/data.py`, lines 18-199

**Attack Vector**:
- Attacker with valid JWT (any role: `viewer`, `operator`, `admin`)
- Calls `GET /v1/regions` → lists ALL regions (no per-region ownership check)
- Calls `GET /v1/detections?camera_id=X` → sees detections from ANY camera, regardless of region ownership
- Calls `GET /v1/plates?region_id=Y` → sees all plates from that region, even if user doesn't manage it
- **Result**: Complete data exfiltration without role-based filtering

Example vulnerable code (data.py, line 122-128):
```python
if camera_id:
    conditions.append(Detection.camera_id == camera_id)
    # ← No check: does current user own this camera? Is user assigned to region?

stmt = select(Detection)
if conditions:
    stmt = stmt.where(and_(*conditions))
# User can query ANY camera_id
```

**Mitigation**:
1. **Add resource ownership validation before querying**:
```python
async def list_detections(
    region_id: str | None = Query(None),
    camera_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),  # Require auth
    role: UserRole = Depends(get_current_user_role),
):
    # Admin can see all regions; others see only assigned regions
    if role == UserRole.ADMIN:
        accessible_region_ids = await db.execute(select(Region.id))
    else:
        accessible_region_ids = await db.execute(
            select(UserRegionAssignment.region_id).where(
                UserRegionAssignment.user_id == user_id
            )
        )
    
    conditions = [Detection.camera.region_id.in_(accessible_region_ids)]
    
    if camera_id:
        conditions.append(Detection.camera_id == camera_id)
    
    stmt = select(Detection).where(and_(*conditions))
    # ... rest of query
```

2. **Create `UserRegionAssignment` table** to map users → regions they can access
3. **Audit logs must record all data access** (who accessed which plates/detections and when)

---

#### **3. WebSocket Token Exposure via Query Parameter (CWE-532, CWE-598)**
**Severity: CRITICAL | Exploitability: 4/5 | Impact: 4/5 | Risk Score: 20**

**Location**: `/Users/saitarrunpitta/Projects/ComputerVision Project/api/routers/websocket.py`, lines 84-104

**Attack Vector**:
```javascript
// In conftest.py (line 363):
websocket_url = f"ws://testserver/v1/stream/test-stream-1?token={token}"
// Token visible in:
// - Browser dev tools Network tab (anyone on same network)
// - Proxy logs / CDN logs / firewall logs
// - HTTP referer headers
// - Browser history
// - Nginx/Apache access logs (default: logs full URL including query params)
```

**Real-world attack**:
- Enterprise network sniffer captures WebSocket URL from logs
- Token extracted and used in new WebSocket connection (token valid for 7 days if refresh token, 60 min if access token)
- Attacker gets live detection stream without re-authenticating

**Mitigation**:
1. **Move token to WebSocket subprotocol or Authorization header** (WebSocket spec allows this):
```python
@router.websocket("/stream/{stream_id}")
async def websocket_endpoint(websocket: WebSocket, stream_id: str):
    # Extract token from Authorization header instead of query param
    auth_header = websocket.headers.get("authorization", "")
    token = auth_header.replace("Bearer ", "") if auth_header else None
    
    if not token or not await verify_ws_token(token):
        await websocket.close(code=1008, reason="Unauthorized")
        return
    
    await websocket.accept()
    # ...
```

2. **Use WebSocket subprotocol (more standard)**:
```python
@router.websocket("/stream/{stream_id}")
async def websocket_endpoint(websocket: WebSocket, stream_id: str):
    subprotocols = websocket.headers.get("sec-websocket-protocol", "").split(",")
    token = None
    for sub in subprotocols:
        if sub.startswith("Bearer "):
            token = sub.replace("Bearer ", "").strip()
            break
    # ... verify token
```

3. **Log sanitization**: Ensure logs NEVER include full URLs or query params:
```python
logger.info(f"WebSocket auth failed for stream={stream_id}")  # Good
logger.info(f"WebSocket URL: {websocket.url}")  # BAD: logs token
```

---

#### **4. No Input Type Validation on UUID Filters (CWE-20, CWE-91)**
**Severity: HIGH | Exploitability: 3/5 | Impact: 4/5 | Risk Score: 15**

**Location**: `/Users/saitarrunpitta/Projects/ComputerVision Project/api/routers/data.py`, lines 122-127

**Attack Vector**:
```python
# data.py: list_detections accepts camera_id as string
if camera_id:
    conditions.append(Detection.camera_id == camera_id)

# Attacker sends: ?camera_id="abc123'; DROP TABLE detections; --"
# ORM should prevent SQL injection, but fuzzy string matching might:
# - Return unexpected results if camera_id type coercion is lenient
# - Cause performance issues if index isn't used (string vs UUID)
# - Trigger database errors leaking schema info
```

**Current State**: Code uses SQLAlchemy ORM (which parameterizes queries), BUT:
- No explicit UUID validation before querying
- `camera_id` is `str | None`, not `UUID`
- Type coercion happens at the DB level (slow, error-prone)

**Mitigation**:
```python
from uuid import UUID as PyUUID

@router.get("/detections", response_model=list[DetectionOut])
async def list_detections(
    region_id: str | None = Query(None),
    camera_id: str | None = Query(None),  # Still accept string from query
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    conditions = []
    
    if camera_id:
        try:
            camera_uuid = PyUUID(camera_id)  # Validate + convert to UUID
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid camera_id format: {camera_id}",
            )
        conditions.append(Detection.camera_id == camera_uuid)
    
    # ... rest of query
```

---

### HIGH

#### **5. Refresh Token Reuse Without Revocation (CWE-613, CWE-384)**
**Severity: HIGH | Exploitability: 4/5 | Impact: 4/5 | Risk Score: 16**

**Location**: `/Users/saitarrunpitta/Projects/ComputerVision Project/api/routers/auth.py`, lines 55-87

**Attack Vector**:
```python
# auth.py refresh endpoint:
@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: dict = Depends(get_current_user),  # Uses access token to refresh!
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    # ...
    return {
        "access_token": access_token,
        "refresh_token": request.get("refresh_token", ""),  # Returns same token!
        "expires_in": settings.jwt_expire_minutes * 60,
    }
```

**Problems**:
1. Refresh endpoint uses `get_current_user`, which validates an **access** token, not a **refresh** token
2. No `verify_token_type(request, "refresh")` call → accepts **any valid JWT**
3. Refresh token never invalidated → stolen token can refresh infinitely
4. No token blacklist/revocation list (Redis cache could track revoked tokens)

**Real attack**: User logs out → attacker steals old refresh token → calls `/refresh` with stolen token → gets fresh access token (valid 60 min) indefinitely.

**Mitigation**:
1. **Verify token type in refresh endpoint**:
```python
from api.security import verify_token_type

@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db_session),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    
    token = authorization.split(" ")[1]
    
    # Verify it's a REFRESH token, not an access token
    try:
        payload = verify_token_type(token, "refresh")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=str(e))
    
    user_id = payload.get("user_id")
    # ... rest of logic
```

2. **Implement token revocation with Redis** (optional but recommended):
```python
async def revoke_token(token: str, redis_client: aioredis.Redis) -> None:
    """Add token to blacklist (Redis)."""
    payload = decode_jwt(token)
    exp = payload.get("exp")
    ttl = exp - int(datetime.now(timezone.utc).timestamp())
    if ttl > 0:
        await redis_client.setex(f"revoked_token:{payload['jti']}", ttl, "1")

# On logout: call revoke_token(access_token); revoke_token(refresh_token)
```

3. **On verify, check if token in blacklist**:
```python
def verify_token(token: str) -> dict:
    payload = decode_jwt(token)
    jti = payload.get("jti")
    if await redis_client.exists(f"revoked_token:{jti}"):
        raise JWTError("Token revoked")
    return payload
```

---

#### **6. Weak Password Policy (CWE-521, CWE-521)**
**Severity: HIGH | Exploitability: 4/5 | Impact: 3/5 | Risk Score: 16**

**Location**: `/Users/saitarrunpitta/Projects/ComputerVision Project/api/security.py`, lines 40-61

**Current check** (line 56):
```python
if len(password) < 8:
    raise PasswordHashError("Password must be at least 8 characters")
```

**Problems**:
- Only enforces **length** (8 chars), not complexity
- Allows `"12345678"` — all numeric, easily brute-forced
- No check for keyboard patterns, dictionary words, or previous breaches
- No rate limiting on password reset / password guessing

**OWASP Guidance**: Minimum 12 characters OR complexity (uppercase + lowercase + digit + special).

**Mitigation**:
```python
import re
from api.config import settings

def validate_password_strength(password: str) -> None:
    """Enforce password complexity requirements."""
    if len(password) < 12:
        raise PasswordHashError("Password must be at least 12 characters")
    
    if not re.search(r'[A-Z]', password):
        raise PasswordHashError("Password must contain uppercase letter")
    
    if not re.search(r'[a-z]', password):
        raise PasswordHashError("Password must contain lowercase letter")
    
    if not re.search(r'[0-9]', password):
        raise PasswordHashError("Password must contain digit")
    
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>?/\\|`~]', password):
        raise PasswordHashError("Password must contain special character")
    
    # Check against common patterns
    common_passwords = {"password", "123456789", "qwerty", "admin", "letmein"}
    if password.lower() in common_passwords:
        raise PasswordHashError("Password too common; choose something unique")

# In hash_password:
def hash_password(password: str) -> str:
    try:
        if not password:
            raise PasswordHashError("Password cannot be empty")
        validate_password_strength(password)  # Add this check
        return pwd_context.hash(password)
    # ...
```

---

#### **7. Credentials Stored in Environment File (CWE-798, CWE-200)**
**Severity: HIGH | Exploitability: 5/5 | Impact: 4/5 | Risk Score: 20**

**Location**: `.env.example` and `.env` (both checked into repo or visible in Docker)

**Current state**:
```bash
JWT_SECRET=change-me-dev-only-jwt-secret-32plus-bytes
S3_ACCESS_KEY=anpr_admin
S3_SECRET_KEY=anpr_dev_pw
DATABASE_URL=postgresql+asyncpg://anpr:anpr_dev_pw@localhost:5432/anpr
```

**Attack vectors**:
1. `.env` accidentally committed to git → forever in history
2. Docker build logs expose secrets if built with `docker build`
3. Kubernetes pods can read `env` from debuggers or log output
4. S3 keys in config used for all operations (no key rotation, no per-user keys)

**Mitigation**:
1. **Use secrets manager** (HashiCorp Vault, AWS Secrets Manager, Google Secret Manager):
```python
# Instead of reading from env, read from Vault
from hvac import Client as VaultClient

def get_secret(secret_path: str, secret_key: str) -> str:
    client = VaultClient(url="https://vault.example.com", token=os.getenv("VAULT_TOKEN"))
    secret = client.secrets.kv.v2.read_secret_version(path=secret_path)
    return secret["data"]["data"][secret_key]

# In config.py:
jwt_secret: str = Field(default_factory=lambda: get_secret("anpr/app", "jwt_secret"))
```

2. **Use AWS Systems Manager Parameter Store** (if on AWS):
```python
import boto3

ssm = boto3.client("ssm")
jwt_secret = ssm.get_parameter(Name="/anpr/jwt-secret", WithDecryption=True)["Parameter"]["Value"]
```

3. **Use Kubernetes Secrets** (if on K8s):
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: anpr-secrets
type: Opaque
stringData:
  jwt-secret: <base64-encoded-secret>
  db-password: <base64-encoded-secret>
---
apiVersion: v1
kind: Pod
metadata:
  name: anpr-api
spec:
  containers:
  - name: api
    env:
    - name: JWT_SECRET
      valueFrom:
        secretKeyRef:
          name: anpr-secrets
          key: jwt-secret
```

4. **Ensure `.env` not in git**:
```bash
echo ".env" >> .gitignore
echo ".env.local" >> .gitignore
```

5. **For S3 credentials**, use:
   - **IAM Roles** (AWS): Pod assumes role, credentials auto-rotated
   - **STS temporary tokens**: Request from STS, expires in 15 min
   - **Per-bucket policies**: Create separate keys for crops, frames, audit (minimize blast radius)

---

#### **8. Insufficient Logging & Monitoring (CWE-778, CWE-532)**
**Severity: HIGH | Exploitability: 2/5 | Impact: 5/5 | Risk Score: 14**

**Location**: Across routers (`auth.py`, `data.py`, `websocket.py`)

**Problems**:
1. **Missing security event logging**:
   - No log on failed login attempts (brute force undetected)
   - No log on token refresh or generation
   - No log on data access (who queried which detections/plates)
   - No log on authorization failures

2. **Logs may leak sensitive data** (line 50, ingest.py):
   ```python
   logger.info(f"Enqueued frame task={task.id} stream={request.stream_id} user={user_id}")
   # OK, but what about base64 frame data? Should NOT log frame_b64_jpeg
   ```

3. **No structured logging** → hard to parse and alert on

**Mitigation**:
```python
import logging
import json
from datetime import datetime

# Structured logging with JSON output
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if hasattr(record, "user_id"):
            log_obj["user_id"] = record.user_id
        if hasattr(record, "action"):
            log_obj["action"] = record.action
        if hasattr(record, "resource"):
            log_obj["resource"] = record.resource
        return json.dumps(log_obj)

# Configure logger:
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger(__name__)
logger.addHandler(handler)

# In auth.py (login):
@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db_session)) -> dict:
    stmt = select(User).where(User.email == request.email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user or not verify_password(request.password, user.hashed_password):
        logger.warning(
            "Login failed: invalid credentials",
            extra={
                "user_email": request.email,
                "action": "login_failure",
                "reason": "invalid_email_or_password",
            }
        )
        raise AuthenticationError("Invalid email or password")
    
    # Success
    logger.info(
        "User logged in",
        extra={
            "user_id": str(user.id),
            "user_email": user.email,
            "action": "login_success",
            "role": user.role.value,
        }
    )
    
    # ... token generation

# In data.py (query):
async def list_detections(..., user_id: str = Depends(get_current_user_id)):
    logger.info(
        "User queried detections",
        extra={
            "user_id": user_id,
            "action": "query_detections",
            "filters": {"camera_id": camera_id, "region_id": region_id},
            "limit": limit,
        }
    )
    # ... query
```

---

#### **9. No Rate Limiting (CWE-770, CWE-636)**
**Severity: HIGH | Exploitability: 5/5 | Impact: 2/5 | Risk Score: 15**

**Location**: All endpoints in `api/routers/`

**Attack vector**:
- Brute-force password: `POST /v1/auth/login` 100 times/sec → lock out legitimate users
- Enumerate resources: `GET /v1/detections?camera_id=X` 1000 times/sec across all UUIDs
- Denial of Service: `POST /v1/ingest/frame` 1000 large frames → CPU spike, Celery queue bloats

**Mitigation**:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

# In main.py:
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# In routers:
@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")  # 5 login attempts per minute per IP
async def login(...):
    # ...

@router.post("/frame", ...)
@limiter.limit("10/minute")  # 10 frame ingests per minute per IP
async def ingest_frame(...):
    # ...

@router.get("/detections")
@limiter.limit("30/minute")  # 30 queries per minute per IP
async def list_detections(...):
    # ...
```

Or use Redis-backed rate limiting for distributed systems:
```python
from slowapi.stores import RedisStore

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="redis://localhost:6379",
    strategy="fixed-window",  # or "moving-window"
)
```

---

### MEDIUM

#### **10. No HTTPS Enforcement (CWE-295, CWE-326)**
**Severity: MEDIUM | Exploitability: 5/5 | Impact: 5/5 | Risk Score: 18** (in production only)

**Location**: `api/main.py` (no TLS middleware)

**Problem**: 
- Dev environment runs on `http://localhost:8000` (fine)
- Production should force HTTPS, but no redirect middleware

**Mitigation**:
```python
# In main.py:
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

if settings.app_env == Environment.PRODUCTION:
    app.add_middleware(HTTPSRedirectMiddleware)

# Also set security headers:
from fastapi.middleware.trustedhost import TrustedHostMiddleware

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[settings.api_host],  # e.g., "api.example.com"
)

# And add HSTS header:
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    if settings.app_env == Environment.PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
    return response
```

---

#### **11. Celery Task Payloads Not Encrypted (CWE-327, CWE-311)**
**Severity: MEDIUM | Exploitability: 3/5 | Impact: 4/5 | Risk Score: 15**

**Location**: `/Users/saitarrunpitta/Projects/ComputerVision Project/api/routers/ingest.py`, line 49

**Problem**:
```python
task = process_frame.delay(request.stream_id, request.frame_b64_jpeg, request.camera_id)
```

- Frame base64 (potentially containing sensitive data) sent to Redis unencrypted
- Redis pubsub also unencrypted (line 52, websocket.py)
- Any Redis client on network can snoop messages

**Mitigation**:
1. **Enable Redis encryption**:
```python
# In config.py:
celery_broker_url = "rediss://localhost:6379"  # rediss = Redis + SSL/TLS
```

2. **Encrypt frame data before queueing** (optional, for defense-in-depth):
```python
from api.security import encrypt_data
from cryptography.fernet import Fernet

# Generate encryption key (store securely in KMS)
encryption_key = Fernet.generate_key()

# Before queueing:
encrypted_frame = encrypt_data(request.frame_b64_jpeg.encode(), encryption_key)
task = process_frame.delay(request.stream_id, encrypted_frame, request.camera_id)

# Worker decrypts:
def process_frame(stream_id, encrypted_frame_b64, camera_id):
    frame_b64 = decrypt_data(encrypted_frame_b64, encryption_key)
    # ... process
```

---

#### **12. Missing Security Headers (CWE-693)**
**Severity: MEDIUM | Exploitability: 2/5 | Impact: 3/5 | Risk Score: 10**

**Location**: `api/main.py` (no security header middleware)

**Missing headers**:
```
Content-Security-Policy: default-src 'self'
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

**Mitigation** (see above in HTTPS enforcement section).

---

#### **13. SQL Injection via String Concatenation (CWE-89, CWE-94)**
**Severity: MEDIUM | Exploitability: 2/5 | Impact: 5/5 | Risk Score: 14**

**Location**: No direct SQL injection found, BUT watchlist regex validation (watchlist.py, line 43-47):
```python
def validate_regex_pattern(pattern: str) -> bool:
    try:
        re.compile(pattern)  # REDoS possible
        return True
    except re.error:
        return False
```

**Problem**: **ReDoS (Regular Expression Denial of Service)**
- Attacker sends `pattern="(a+)+b"` → regex engine hangs
- CPU spike, service unavailable

**Mitigation**:
```python
import re
import signal

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Regex compilation timeout")

def validate_regex_pattern(pattern: str, timeout_sec: float = 1.0) -> bool:
    """Validate regex with timeout to prevent ReDoS."""
    try:
        # Set alarm to timeout
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(int(timeout_sec))
        
        re.compile(pattern)
        
        signal.alarm(0)  # Cancel alarm
        return True
    except TimeoutError:
        logger.error(f"Regex compilation timeout: {pattern}")
        return False
    except re.error as e:
        logger.error(f"Invalid regex: {pattern} - {e}")
        return False
    finally:
        signal.alarm(0)
```

Or use safer regex library:
```python
import regex  # pip install regex

def validate_regex_pattern(pattern: str) -> bool:
    try:
        # regex library has better backtracking controls
        regex.compile(pattern, timeout=1)  # 1 sec timeout
        return True
    except (regex.error, regex.TimeoutError):
        return False
```

---

### LOW

#### **14. Missing Input Validation on Plate String (CWE-20)**
**Severity: LOW | Exploitability: 1/5 | Impact: 2/5 | Risk Score: 2**

**Problem**: No regex validation on `plate_string` before storing
- Could store XSS payload: `<img src=x onerror=alert('xss')>`
- Frontend must escape on render (good defense-in-depth)

**Mitigation**:
```python
# In watchlist.py or plate model:
def validate_plate_string(plate_string: str, region: Region) -> bool:
    """Validate plate matches region's regex."""
    return bool(re.match(region.regex, plate_string))

# Before storing:
if not validate_plate_string(plate_string, region):
    raise ValidationError(f"Plate {plate_string} doesn't match region format")
```

---

#### **15. Debug Router Exposed in Non-Prod (CWE-215)**
**Severity: LOW | Exploitability: 3/5 | Impact: 2/5 | Risk Score: 6**

**Location**: `api/main.py`, lines 113-114

```python
if settings.app_env.value != "production":
    app.include_router(debug.router)
```

**Problem**: `/debug` endpoints may expose system state, model paths, etc.

**Mitigation**:
```python
# In main.py:
if settings.app_env == Environment.DEV:
    app.include_router(debug.router)
    # Remove docs in production
else:
    app.openapi_url = None  # Disable OpenAPI schema endpoint
    app.docs_url = None     # Disable Swagger UI
    app.redoc_url = None    # Disable ReDoc
```

---

## Security Requirements Checklist

### Authentication & Session Management
- [ ] Enforce strong password policy (12+ chars, complexity)
- [ ] Hash passwords with Argon2 or bcrypt (✓ done)
- [ ] Implement token revocation (Redis blacklist)
- [ ] Verify token type (access vs. refresh) in refresh endpoint
- [ ] Set secure cookie flags (HttpOnly, Secure, SameSite) if using cookies
- [ ] Implement logout endpoint that revokes tokens
- [ ] Add rate limiting on login endpoint (5/min)

### Authorization & Access Control
- [ ] Implement per-resource authorization checks (who can access which regions/cameras)
- [ ] Create `UserRegionAssignment` table
- [ ] Validate user ownership before returning data
- [ ] Implement RBAC for admin/operator/viewer roles
- [ ] Audit all data access attempts

### Input Validation
- [ ] Validate all UUID inputs (use `uuid.UUID()` before querying)
- [ ] Validate regex patterns with timeout (prevent ReDoS)
- [ ] Validate base64 frame data (size, format)
- [ ] Validate all query parameters (limit bounds, string lengths)
- [ ] Sanitize error messages (no stack traces to clients)

### Cryptography & Secrets
- [ ] Store JWT secret in secrets manager (Vault, KMS, or K8s Secrets)
- [ ] Store S3 keys in secrets manager
- [ ] Use TLS for Redis (rediss://) and PostgreSQL connections
- [ ] Encrypt frames in transit (S3-side encryption enabled)
- [ ] Rotate S3 keys quarterly (implement key versioning)
- [ ] Never log passwords, tokens, or API keys

### Logging & Monitoring
- [ ] Log all authentication events (login, logout, token refresh, failures)
- [ ] Log all authorization failures (user denied access to resource)
- [ ] Log all data access (user queried detections/plates, with filters)
- [ ] Use structured logging (JSON format for easy parsing)
- [ ] Monitor failed login attempts (alert on >10 failures/min from single IP)
- [ ] Monitor token usage (alert on refresh >5x/hour from same user)
- [ ] Monitor data access patterns (alert on unusual region queries)
- [ ] Retain audit logs for 90+ days (compliance)

### CORS & CSRF
- [ ] Remove wildcard CORS origin (`*`)
- [ ] Explicitly whitelist frontend origin(s)
- [ ] Disable `allow_credentials` if using `*` origin
- [ ] Implement CSRF token validation (if using cookies)
- [ ] Set `SameSite=Strict` on cookies

### Error Handling
- [ ] Return generic error messages to clients (no stack traces)
- [ ] Log detailed errors server-side only
- [ ] Avoid error messages that reveal schema (e.g., "user_id not found" → just "unauthorized")

### Dependency Management
- [ ] Regularly update dependencies (pip, npm)
- [ ] Use `pip-audit` or `safety` to check for known vulnerabilities
- [ ] Pin versions in requirements.txt (no `*` or `>=` without upper bound)
- [ ] Review dependency licenses (no GPL in commercial code)

### Infrastructure
- [ ] Enforce HTTPS in production (HTTP → HTTPS redirect)
- [ ] Set HSTS header (Strict-Transport-Security)
- [ ] Configure database with TLS (postgresql+asyncpg+sslmode=require)
- [ ] Implement network segmentation (API, database, Redis on separate VPCs)
- [ ] Use IAM roles for cloud credential access (no embedded keys)
- [ ] Enable database audit logging
- [ ] Implement DDoS protection (CloudFlare, AWS Shield, etc.)

### WebSocket Security
- [ ] Move token from query param to Authorization header
- [ ] Implement per-user isolation (user only sees streams they own)
- [ ] Validate `stream_id` ownership before subscribing
- [ ] Sanitize logs (don't log full WebSocket URLs)

---

## Verification Plan

### Security Testing
1. **Authentication Testing**:
   - [ ] Attempt login with invalid credentials (verify generic error message)
   - [ ] Attempt login with >10 invalid passwords in 1 minute (verify rate limit)
   - [ ] Refresh access token with refresh token (verify token type check)
   - [ ] Attempt to refresh with access token (should fail)
   - [ ] Logout and verify token can't be used (revocation check)

2. **Authorization Testing**:
   - [ ] As user A, query detections from region B (user A doesn't manage)
   - [ ] Verify HTTP 403 Forbidden response
   - [ ] Admin queries all regions (verify success)
   - [ ] Operator queries only assigned regions (verify)

3. **Input Validation Testing**:
   - [ ] `GET /v1/detections?camera_id=invalid-uuid` (verify 422 response)
   - [ ] `GET /v1/detections?limit=10000` (verify clamped to 1000)
   - [ ] `POST /v1/watchlist` with regex `(a+)+b` (verify timeout or rejection)

4. **CORS Testing**:
   - [ ] Curl from `https://attacker.com` with `Origin: https://attacker.com` header
   - [ ] Verify response does NOT include `Access-Control-Allow-Origin: *`
   - [ ] Verify credentials header not sent

5. **Logging Testing**:
   - [ ] Trigger login failure, verify `login_failure` event in logs (no password)
   - [ ] Query detections, verify `query_detections` event in logs
   - [ ] Verify no tokens, passwords, or API keys in logs

### Automated Testing
- **SAST**: Run `bandit` (Python security linter) on all routers
  ```bash
  bandit -r api/ -ll  # Low + Medium + High severity
  ```
- **Dependency audit**: `pip-audit` to check for known CVEs
  ```bash
  pip-audit
  ```
- **DAST**: Use Burp Suite or OWASP ZAP to test endpoints
  - Test CORS headers
  - Test input validation
  - Test authorization bypass

### Monitoring & Alerting
1. **CloudWatch / Prometheus metrics**:
   - `auth_login_failures_total` (counter, labeled by email)
   - `auth_token_refresh_total` (counter)
   - `data_query_total` (counter, labeled by user_id, region_id, action)
   - `http_request_duration_seconds` (histogram)

2. **Alerting rules**:
   - Alert if `auth_login_failures_total > 10` in 5 min from single IP
   - Alert if `auth_token_refresh_total > 5` in 1 hour from single user
   - Alert if `http_requests` for `/v1/` endpoint > 1000 req/min from single IP (DoS)
   - Alert on any HTTP 403 (authorization failure)

### Post-Deployment
- [ ] Run penetration test 2 weeks after deploying security fixes
- [ ] Conduct security review of all new endpoints before merging
- [ ] Quarterly dependency and security posture audit
- [ ] Document all security decisions and exceptions in SECURITY.md

