---
name: m6_api_fixes_test_coverage
description: Test coverage for 5 critical M6 API fixes (auth, UUID validation, type conversion)
metadata:
  type: project
---

## 5 Critical API Fixes (Deployed)

1. **/v1/regions requires auth** – Added `Depends(get_current_user_id)`
2. **/v1/regions/{region_id}/cameras validates UUID** – Returns 422 on invalid format
3. **/v1/regions/{region_id}/cameras checks region exists** – Returns 404 if not found
4. **/v1/regions/{region_id}/cameras fixes type mismatch** – Changed str → UUID in filter query
5. **/v1/auth/refresh fixes token lookup** – Changed "sub" → "user_id" field extraction

## Test Suite

**Location:** `/tests/integration/test_data_endpoints.py`
**Total:** 19 passing tests
- 8 tests: /v1/regions auth requirement (fix #1)
- 9 tests: /v1/regions/{region_id}/cameras validation (fixes #2, #3, #4)
- 2 tests: /v1/auth/refresh token handling (fix #5)

**Key Coverage:**
- Happy paths (200 OK responses with correct data)
- Error conditions (401, 404, 422 with proper detail messages)
- Edge cases (UUID case sensitivity, format variations)
- Schema validation (all required fields present, correct types)
- Role-based access (viewer, operator, admin roles)

## Infrastructure Fix

**File:** `/tests/conftest.py`
**Change:** JWT secret fixture now uses `settings.jwt_secret` instead of hardcoded fallback

**Why:** Test tokens generated with app settings secret so they validate correctly
in dependency verification. Enables proper JWT auth testing in test client.

## Test Patterns

**Auth tests:** Use `auth_token_factory` fixture to generate valid JWT, set Authorization header
**UUID tests:** Verify error codes (422/404) and normalize UUID formats
**Schema tests:** Iterate required_fields list, check types in response
**Role tests:** Create tokens for viewer/operator/admin, verify access

## Running Tests

```bash
# All API fix tests
pytest tests/integration/test_data_endpoints.py -v

# By fix area
pytest tests/integration/test_data_endpoints.py::TestRegionsEndpoints -v
pytest tests/integration/test_data_endpoints.py::TestCamerasEndpoints -v
pytest tests/integration/test_data_endpoints.py::TestTokenRefreshFix -v
```

## Artifacts

- Test file: `tests/integration/test_data_endpoints.py`
- Reference doc: `TESTING_API_FIXES.md` (maps fixes to tests)
- Git commit: `b7f0846` – "Add comprehensive test suite for 5 critical API fixes"
