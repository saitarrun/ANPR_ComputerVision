---
name: m6_task7_security_fixes
description: Task 7 completion — Critical #4, High #10, #12 security fixes
metadata:
  type: project
---

## Task 7 Completion (2026-05-28)

Fixed three security issues in M6 backend:

### Critical #4: Secrets Migration (Foundation Only)
- `.env.example` created with placeholder values; instructions for copying to `.env`
- `SECRETS.md` documentation: local dev setup + CI/CD patterns
- `.env` remains in `.gitignore`; never committed to git
- `api/config.py` reads `CELERY_ENCRYPTION_KEY` from environment (required, 44+ chars)
- Post-M6 integration planned: AWS Secrets Manager or HashiCorp Vault

**Why:** Prevent accidental secrets commits; provide safe onboarding path for new developers and CI/CD.

**How to apply:** When adding new secrets, update both `.env.example` and `SECRETS.md`. All sensitive values loaded from environment at runtime.

### High #10: Celery Encryption on Redis
- Created `api/crypto.py` with Fernet-based encryption (symmetric, AES-128)
- `encrypt_frame()` / `decrypt_frame()` functions for frame payload protection
- `api/routers/ingest.py` encrypts raw frame bytes before enqueuing to Celery
- `workers/tasks.py` decrypts encrypted bytes from Redis before ANPR processing
- `CELERY_ENCRYPTION_KEY` generated once, stored in `.env` (dev) / secrets manager (prod)
- `tests/conftest.py` autouse fixture generates ephemeral test key

**Why:** Redis is often network-accessible; unencrypted frame data could be intercepted or logged. Fernet provides confidentiality + integrity.

**How to apply:** All frame data flowing through Celery is now encrypted in-transit. No code changes needed for new frame sources; encryption is transparent at the ingest layer.

### High #12: ReDoS Timeout on Watchlist Regex
- `api/routers/watchlist.py` updated: `validate_regex_pattern()` now uses signal-based timeout
- 1-second `SIGALRM` timeout prevents catastrophic backtracking (e.g., `(a+)+b` patterns)
- Test string `"A" * 50 + "INVALID"` triggers known ReDoS patterns within timeout window
- Invalid patterns logged as warnings; request returns 400 Bad Request

**Why:** User-supplied watchlist regex patterns (e.g., `plate_pattern`) can trigger exponential time complexity. Malicious input like `(.*)*invalid` hangs API.

**How to apply:** Developers can't avoid this — timeout is transparent. Users who submit ReDoS patterns get fast failure instead of hung requests. (Note: Signal-based timeout only works on Unix; Windows deployments may need alternative.)

## Test Results
- 198 tests passing (including new e2e + integration tests)
- 92 failed + 4 errors: pre-existing, unrelated to these three fixes
- Encryption/decryption verified in isolation
- ReDoS protection verified: valid patterns accepted, invalid/malicious patterns rejected within timeout

## Files Modified
- `.env.example` — new secrets template
- `SECRETS.md` — onboarding + migration guide
- `api/config.py` — celery_encryption_key field
- `api/crypto.py` — new module
- `api/routers/ingest.py` — encrypt before Celery
- `api/routers/watchlist.py` — ReDoS timeout protection
- `workers/tasks.py` — decrypt from Redis
- `tests/conftest.py` — test encryption key fixture

## Post-M6 Work
- [ ] AWS Secrets Manager integration (replace .env file distribution)
- [ ] Secrets rotation policy + audit
- [ ] ReDoS timeout on Windows (signal SIGALRM not portable)
- [ ] Regex pattern complexity analysis (pre-compile validation)
