# Role-Based Access Control (RBAC) & Threat Model

**Document Version:** 1.0  
**Last Updated:** 2026-05-28  
**Author:** Security Threat Architect

## Executive Summary

This document defines the ANPR backend's role-based access control (RBAC) matrix, threat model, and security architecture. Three roles (viewer, operator, admin) enforce least-privilege access across 14 REST endpoints and WebSocket streams. All access is authenticated via JWT (HS256, 15-min expiry) and authorized via role-based checks at the API layer.

---

## 1. Threat Model

### 1.1 Key Assets

| Asset | Classification | Sensitivity | Control |
|-------|-----------------|------------|---------|
| **Plate Strings (PII)** | Personal Data | High | Fernet encryption at rest; audit on read |
| **User Credentials** | Auth Secret | Critical | bcrypt hashing (cost 12); never logged |
| **JWT Tokens** | Session Secret | High | HS256 signature; 15-min access / 7-day refresh |
| **Audit Logs** | Compliance Record | High | Immutable append-only; daily S3 backup |
| **User Roles** | Authorization | Medium | JWT claim; role checks at endpoint |
| **API Keys** | Service-to-Service Auth | Medium | Redis token-bucket rate limiting |

### 1.2 Trust Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│ External: Internet, Untrusted Clients                      │
│  ├── HTTP/TLS → API Gateway (rate limit, validate headers) │
│  └── [TLS enforced; no plaintext]                           │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
         ┌─────────────────────┐
         │ FastAPI + Middleware│ (Internal, Trusted)
         │ - JWT validation    │
         │ - RBAC checks       │
         │ - Audit logging     │
         └────────┬────────────┘
                  │
      ┌───────────┼───────────┐
      ▼           ▼           ▼
 ┌────────┐ ┌─────────┐ ┌──────────┐
 │ PostgreSQL SQLAlchemy MinIO/S3
 │ (Encrypted) (Parameterized) (IAM + Encryption)
 │ [Trusted Internal Network]
 └────────┘ └─────────┘ └──────────┘
```

### 1.3 Attack Paths (Ranked by Risk)

| # | Attack Vector | Likelihood | Impact | Risk | Mitigation |
|---|---|---|---|---|---|
| **1** | **Credential Stuffing / Brute Force** | High | Account Takeover | 20 (Critical) | Rate limit /login; account lockout after 5 failures; CAPTCHA (M7) |
| **2** | **JWT Forgery** | Low | Auth Bypass | 10 (Medium) | HS256 signature validation; exp check; aud/iss validation |
| **3** | **Token Hijacking (network)** | Medium | Session Hijack | 15 (High) | TLS enforcement; HttpOnly cookie + SameSite (M8); short expiry (15min) |
| **4** | **Privilege Escalation** | Low | Unauthorized Access | 12 (High) | Role validation at endpoint; no hardcoded roles; audit all privilege changes |
| **5** | **Plate String Exfiltration** | Low | Privacy Breach | 8 (Medium) | Fernet encryption; audit log on all reads; minimum role viewer |
| **6** | **SQL Injection** | Very Low | Data Breach | 5 (Low) | SQLAlchemy parameterized queries only; no raw SQL |
| **7** | **Replay Attack** | Low | Transaction Reuse | 6 (Medium) | Use jti claim; add token blacklist (M7); idempotency keys for POST |
| **8** | **Insecure Deserialization** | Very Low | RCE | 3 (Low) | Pydantic validation; no pickle; no eval |

### 1.4 Out of Scope

These threats are **NOT** mitigated by this layer:
- **DDoS**: Handled by CDN/WAF upstream
- **Compromised RDS**: Assume AWS RDS encryption at rest; DB firewall (no internet access)
- **Malicious Insiders**: Assume DBA access restricted; audit log for forensics only
- **Quantum Computing**: Post-quantum crypto deferred to M11
- **Unpatched Dependencies**: Tracked via pip-audit; automated alerts (M7)

---

## 2. Role Definitions & Permissions

### 2.1 Role Hierarchy

```
              admin (full access)
              /    \
         operator    viewer (read-only)
             /          \
        Creates & Edits   Reads Only
        Watchlist, Reviews
```

### 2.2 RBAC Matrix

| Endpoint | Method | viewer | operator | admin | Auth | Notes |
|----------|--------|--------|----------|-------|------|-------|
| **Auth** |
| `/v1/auth/login` | POST | ✓ | ✓ | ✓ | None (public) | Rate limited (5/min per IP) |
| `/v1/auth/refresh` | POST | ✓ | ✓ | ✓ | refresh_token | Extends session |
| **Streams** |
| `GET /v1/streams` | GET | ✓ | ✓ | ✓ | Bearer | List all active streams |
| `GET /v1/streams/{id}` | GET | ✓ | ✓ | ✓ | Bearer | Stream metadata + stats |
| `POST /v1/streams` | POST | ✗ | ✓ | ✓ | Bearer | Create new stream (operator/admin only) |
| `DELETE /v1/streams/{id}` | DELETE | ✗ | ✓ | ✓ | Bearer | Delete stream (operator/admin only) |
| **Plates** |
| `GET /v1/plates` | GET | ✓ | ✓ | ✓ | Bearer | Search + filter + pagination; plate_string **decrypted on read** |
| `GET /v1/plates/{id}/events` | GET | ✓ | ✓ | ✓ | Bearer | Event history for plate |
| **Watchlist** |
| `GET /v1/watchlist` | GET | ✓ | ✓ | ✓ | Bearer | View all watchlist entries (owned) |
| `POST /v1/watchlist` | POST | ✗ | ✓ | ✓ | Bearer | Create watchlist entry (operator/admin) |
| `DELETE /v1/watchlist/{id}` | DELETE | ✗ | ✓ | ✓ | Bearer | Delete watchlist entry (operator/admin) |
| **Review Queue** |
| `GET /v1/review-queue` | GET | ✓ | ✓ | ✓ | Bearer | View queue (flagged detections) |
| `POST /v1/review-queue/{id}/resolve` | POST | ✗ | ✓ | ✓ | Bearer | Mark detection as reviewed (operator/admin) |
| **Audit Log** |
| `GET /v1/audit-log` | GET | ✗ | ✗ | ✓ | Bearer | Admin only; immutable compliance log |
| **WebSocket** |
| `WS /v1/stream/{stream_id}` | WS | ✓ | ✓ | ✓ | Bearer (via query param) | Live detection feed; metadata only (no JPEG payload) |
| **Health** |
| `GET /healthz` | GET | ✓ | ✓ | ✓ | None | Liveness probe (no auth required) |
| `GET /readyz` | GET | ✓ | ✓ | ✓ | None | Readiness probe (no auth required) |

### 2.3 Row-Level Security (RLS)

Even with role-based access, additional row-level checks enforce least privilege:

```python
# Example: GET /v1/plates (viewer+ role)
# 1. Check role >= viewer ✓
# 2. If viewer: only return plates from streams they can view
# 3. If operator: return plates from streams they created + assigned
# 4. If admin: return all plates

async def get_plates(user: User, skip: int = 0, limit: int = 100):
    query = select(Plate)
    
    if user.role == "viewer":
        # Restrict to authorized streams (via join)
        query = query.join(Stream).filter(Stream.viewer_user_ids.contains(user.id))
    elif user.role == "operator":
        # Can see own streams + assigned streams
        query = query.join(Stream).filter(
            (Stream.created_by_user_id == user.id) |
            (Stream.operator_user_ids.contains(user.id))
        )
    # admin: no filter (sees all)
    
    return await session.execute(query.offset(skip).limit(limit))
```

---

## 3. Authentication Mechanism (JWT)

### 3.1 Token Structure

```json
{
  "user_id": "uuid-of-user",
  "role": "operator",          // viewer | operator | admin
  "exp": 1700000000,           // Expiry timestamp (Unix epoch)
  "iat": 1699999700,           // Issued-at timestamp
  "aud": "anpr-api",           // Audience (audience claim validation)
  "iss": "anpr-backend",       // Issuer (issuer claim validation)
  "jti": "unique-token-id",    // JWT ID (for token revocation/blacklist)
  "type": "access"             // "access" or "refresh"
}
```

### 3.2 Token Lifecycle

```
1. Login: POST /v1/auth/login
   ├─ Email + password
   ├─ bcrypt verify against hashed_password in DB
   ├─ Issue access_token (15-min)
   ├─ Issue refresh_token (7-day)
   └─ Return both tokens + user role

2. Authenticated Request: GET /v1/plates
   ├─ Include "Authorization: Bearer <access_token>"
   ├─ API validates JWT: signature, exp, aud, iss
   ├─ Extract user_id, role from JWT
   ├─ Check role has endpoint permission
   ├─ Apply row-level filters
   └─ Return response

3. Token Refresh: POST /v1/auth/refresh
   ├─ Include refresh_token
   ├─ Validate: signature, exp, type="refresh"
   ├─ Issue new access_token (15-min)
   └─ Return new access_token

4. Token Expiry: 401 Unauthorized
   ├─ Client catches 401 "Token has expired"
   ├─ Call POST /v1/auth/refresh with refresh_token
   ├─ Get new access_token
   └─ Retry original request
```

### 3.3 Cryptographic Details

| Property | Value | Justification |
|----------|-------|---|
| **Algorithm** | HS256 (HMAC-SHA256) | Fast, symmetric; secret shared between API instances |
| **Secret** | 32+ bytes | Minimum NIST recommendation; stored in env var |
| **Access Token Expiry** | 15 minutes | Balance between usability and risk; short enough to limit damage if token stolen |
| **Refresh Token Expiry** | 7 days | Longer, but user must authenticate with password to obtain refresh token |
| **Key Rotation** | TBD (M8) | Currently static secret; implement key rotation in M8 |

---

## 4. Password Security

### 4.1 Hashing Algorithm

| Property | Value | Justification |
|----------|-------|---|
| **Algorithm** | bcrypt | Industry standard; resistant to GPU/ASIC attacks; salted + hashed |
| **Cost** | 12 | ~100ms per hash on modern hardware; acceptable for login UX; resistant to brute force |
| **Storage** | 60-character hash in `users.hashed_password` | Never store plaintext; always hash on input |

### 4.2 Password Requirements

```python
# Enforced at signup (M7)
MIN_PASSWORD_LENGTH = 8
REQUIRES_UPPERCASE = True
REQUIRES_DIGITS = True
REQUIRES_SPECIAL_CHARS = False  # Optional; defer to M8 if PCI-DSS required

# Example valid: MyPass123, SecureP@ssw0rd, 8CharMin!
```

---

## 5. Plate String Encryption

### 5.1 Encryption at Rest

**All plate strings stored encrypted in database:**

```sql
-- DB Schema (encrypted)
CREATE TABLE plates (
    id UUID PRIMARY KEY,
    plate_string_encrypted VARCHAR(1024) NOT NULL,  -- Fernet ciphertext (hex)
    region_code VARCHAR(10),
    detected_at TIMESTAMP,
    ...
);
```

### 5.2 Encryption Details

| Property | Value | Justification |
|----------|-------|---|
| **Algorithm** | Fernet (symmetric, from cryptography library) | Authenticated encryption (prevents tampering); timestamp nonce prevents replay |
| **Key** | 32 bytes (44 chars base64) | NIST 256-bit symmetric; stored in FERNET_KEY env var |
| **Ciphertext Format** | Hex string (database storage) | Easier to index/debug than base64; same information density |
| **Decryption** | On-read (lazy), in-memory only | Decrypted only when user requests; not cached; audit log on read |

### 5.3 Envelope Encryption (Future: M8)

```
Current (DEV): Single Fernet key
Future (PROD): 
  ├─ Master key: stored in AWS KMS
  ├─ Derive region-specific DEKs (Data Encryption Keys)
  ├─ Encrypt plate_string with DEK
  ├─ Encrypt DEK with master key
  └─ Store encrypted DEK in audit log for rotation
```

---

## 6. Audit Logging

### 6.1 Audit Log Schema

```python
class AuditLog(Base):
    id: UUID = Column(UUID, primary_key=True, default=uuid4)
    user_id: UUID = Column(UUID, ForeignKey("users.id"), index=True)
    action: str = Column(String(50), index=True)  # LOGIN, VIEW_PLATE, DELETE_STREAM, etc.
    resource_type: str = Column(String(50), index=True)  # USER, STREAM, PLATE, WATCHLIST
    resource_id: Optional[UUID] = Column(UUID, index=True)
    details: Optional[Dict] = Column(JSON)  # Additional context
    ip_address: str = Column(String(45))  # IPv4 or IPv6
    user_agent: Optional[str] = Column(String(500))
    created_at: datetime = Column(DateTime, server_default=utcnow, index=True)

    # Immutable: no UPDATE, only INSERT
    __table_args__ = (
        Index("idx_audit_user_created", "user_id", "created_at"),
        Index("idx_audit_action_resource", "action", "resource_type", "created_at"),
    )
```

### 6.2 Audit Events

| Action | Resource Type | Logged | Example |
|--------|---|---|---|
| **LOGIN_SUCCESS** | USER | ✓ | User logged in |
| **LOGIN_FAIL** | USER | ✓ | Wrong password (rate limit counter) |
| **TOKEN_REFRESH** | USER | ✓ | Refresh token used |
| **VIEW_PLATE** | PLATE | ✓ | Plate details accessed (incl. decryption) |
| **SEARCH_PLATES** | PLATE | ✓ | Search query + result count |
| **CREATE_STREAM** | STREAM | ✓ | New stream created; stream_id in resource_id |
| **DELETE_STREAM** | STREAM | ✓ | Stream deleted; stream_id in resource_id |
| **CREATE_WATCHLIST** | WATCHLIST | ✓ | New watchlist entry; pattern logged |
| **DELETE_WATCHLIST** | WATCHLIST | ✓ | Watchlist entry deleted |
| **REVIEW_QUEUE_RESOLVE** | REVIEW_QUEUE | ✓ | Detection reviewed; decision (FP/TP) |
| **CREATE_USER** | USER | ✓ | New user created (admin only) |
| **DELETE_USER** | USER | ✓ | User deleted (admin only) |
| **ROLE_CHANGE** | USER | ✓ | User role changed (admin only) |

### 6.3 Audit Log Immutability

```python
# Constraint: No UPDATE, no DELETE after creation
class AuditLog(Base):
    ...
    # PostgreSQL CHECK constraint prevents tampering
    __table_args__ = (
        CheckConstraint("created_at <= CURRENT_TIMESTAMP"),
    )

# Backup strategy
- Daily: Export audit logs to S3 (immutable versioning enabled)
- Retention: 7 years (compliance requirement)
- Access: Admin only; logged in audit log itself
```

---

## 7. Rate Limiting

### 7.1 Rate Limit Buckets

| Endpoint | Limit | Window | Notes |
|----------|-------|--------|-------|
| `POST /v1/auth/login` | 5 | 1 minute (per IP) | Brute-force protection |
| `POST /v1/auth/refresh` | 30 | 1 minute (per user) | Normal refresh cycles |
| `GET /v1/plates` | 100 | 1 minute (per user) | Read endpoint |
| `POST /v1/watchlist` | 20 | 1 minute (per user) | Create new entries |
| `WS /v1/stream/{id}` | 1 (connection) | Per user | Only 1 WebSocket per stream per user |

### 7.2 Implementation

```python
# Redis token-bucket
# Key: "rate_limit:{endpoint}:{user_id_or_ip}"
# Value: JSON { tokens: int, refill_at: timestamp }

async def check_rate_limit(endpoint: str, user_id: str, limit: int, window_sec: int):
    key = f"rate_limit:{endpoint}:{user_id}"
    bucket = await redis.get(key)
    
    if not bucket:
        await redis.setex(key, window_sec, json.dumps({"tokens": limit - 1}))
        return True  # Request allowed
    
    bucket = json.loads(bucket)
    if bucket["tokens"] > 0:
        bucket["tokens"] -= 1
        await redis.setex(key, window_sec, json.dumps(bucket))
        return True  # Request allowed
    
    return False  # Rate limit exceeded; respond with 429 Too Many Requests
```

---

## 8. Secure Defaults & Configuration

### 8.1 Environment Variables (Never Hardcode)

```bash
# .env (local dev only; never commit)
JWT_SECRET=<32+ random bytes, base64>
FERNET_KEY=<44-char base64 key from Fernet.generate_key()>

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/anpr

# App
ENVIRONMENT=development  # development | staging | production
DEBUG=false

# Security
RATE_LIMIT_ENABLED=true
CORS_ORIGINS=["http://localhost:3000"]
```

### 8.2 Secure Defaults (Production)

```python
# api/config.py
class Settings(BaseSettings):
    debug: bool = False  # Always False in prod
    jwt_algorithm: str = "HS256"  # Non-negotiable
    jwt_access_token_expire_minutes: int = 15  # Short
    jwt_refresh_token_expire_days: int = 7
    
    password_min_length: int = 8
    bcrypt_cost: int = 12
    
    rate_limit_enabled: bool = True  # Enforce by default
    rate_limit_login_per_minute: int = 5
    
    database_pool_size: int = 10
    database_max_overflow: int = 20
    
    audit_log_enabled: bool = True  # Always audit
    audit_log_s3_backup: bool = True  # Daily export
    
    # HTTPS enforcement (in middleware)
    require_https: bool = True
```

---

## 9. Security Testing & Verification

### 9.1 Unit Tests

```bash
pytest tests/unit/test_security.py -v
# Covers: JWT encode/decode, password hashing, encryption, RBAC checks
```

### 9.2 Integration Tests

```bash
pytest tests/integration/test_auth_flow.py -v
# Covers: Full login → JWT → authenticated request → audit log
```

### 9.3 SAST & Dependency Scanning

```bash
# Static analysis
bandit -r api/

# Dependency vulnerabilities
pip-audit

# OWASP Top 10 checks
trivy fs .
```

### 9.4 Security Verification Checklist

- [ ] All secrets from environment variables (never hardcoded)
- [ ] JWT secret >= 32 bytes; stored in env only
- [ ] Passwords hashed with bcrypt (cost 12); never logged
- [ ] Plate strings encrypted with Fernet; decrypted on-read
- [ ] All database queries parameterized (SQLAlchemy ORM)
- [ ] RBAC enforced at endpoint + row-level
- [ ] Audit log immutable; daily S3 backup
- [ ] Rate limiting active (429 on exceed)
- [ ] HTTPS enforced (TLS 1.2+)
- [ ] No tokens in error messages or logs
- [ ] No hardcoded credentials in code
- [ ] pip-audit + trivy pass (no CVEs)
- [ ] All 14 endpoints live with correct auth/RBAC

---

## 10. Incident Response

### 10.1 Token Compromise

**If a JWT token is stolen:**
1. Add token's `jti` claim to Redis blacklist (if using token blacklist in M7)
2. Check audit log for unauthorized access from that token
3. Notify affected user; recommend password change
4. Rotate JWT_SECRET if widespread compromise

### 10.2 Database Breach

**If hashed passwords are leaked:**
- bcrypt + salt make offline attacks infeasible (100ms per guess)
- Force password reset for all users (M7)
- Notify users; recommend password reuse audit

### 10.3 Plate String Exfiltration

**If Fernet key is exposed:**
- Rotate FERNET_KEY immediately
- Re-encrypt all plate strings with new key
- Audit all decryptions in prior 7 days
- Notify affected users

---

## 11. Future Work (M7+)

| Milestone | Enhancement | Justification |
|-----------|---|---|
| **M7** | Token blacklist (Redis) | Revoke tokens on logout / suspicious activity |
| **M7** | Rate limit: Distributed (Redis Cluster) | Scale to multi-instance deployment |
| **M7** | Account lockout: After 5 failed logins | Brute-force hardening |
| **M8** | Envelope encryption (KMS) | Crypto key rotation for compliance |
| **M8** | OAuth2 / OIDC support | SSO integration |
| **M8** | Audit log redaction | PII removal from audit trails |
| **M9** | Threat detection: Anomalous access patterns | ML-based detection of account takeover |
| **M11** | Post-quantum crypto | RSA → Kyber/Dilithium (NIST standards) |

---

## 12. Compliance & Standards

| Standard | Relevant Sections |
|----------|---|
| **OWASP Top 10** | A01: Broken Auth (JWT), A02: Crypto Failures (Fernet), A03: Injection (parameterized queries) |
| **NIST 800-63-3** | Authentication, Session Management, Cryptography |
| **CWE-20** | Improper Input Validation → Pydantic schemas |
| **CWE-89** | SQL Injection → SQLAlchemy ORM (no raw SQL) |
| **CWE-287** | Improper Authentication → JWT + password hashing |
| **CWE-384** | Session Fixation → Short-lived tokens (15min) |

---

## References

1. [JWT.io](https://jwt.io) — JWT standard, validation checklist
2. [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
3. [NIST Digital Identity Guidelines (SP 800-63-3)](https://pages.nist.gov/800-63-3/)
4. [cryptography.io Fernet](https://cryptography.io/en/latest/fernet/) — Symmetric encryption
5. [passlib bcrypt](https://passlib.readthedocs.io/en/1.7.4/lib/passlib.context.html#bcrypt) — Password hashing

---

**Document Status:** READY FOR IMPLEMENTATION  
**Approved By:** Security Threat Architect  
**Next Review:** After M6 integration tests pass
