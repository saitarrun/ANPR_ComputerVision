---
name: anpr-schema-design
description: 9-table PostgreSQL ANPR schema with 11 FK constraints, indexes, and append-only audit logging
metadata:
  type: reference
---

## Canonical 9-Table ANPR Schema (DL-001)

**Status:** Committed in commit 8c5fbc9 (M6 branch)

### Core Tables

1. **regions** (dimension)
   - PK: id
   - UK: code (e.g., 'CA', 'UK', 'JP')
   - Fields: name, regex_pattern, charset_whitelist, char_confusion_map (JSON)
   - Used by: cameras, plates, watchlist entries

2. **users** (access control)
   - PK: id
   - UK: email
   - Fields: role (viewer|operator|admin), hashed_password (bcrypt), is_active
   - CHECK: role IN ('viewer', 'operator', 'admin')
   - Used by: cameras (created_by), audit_log, api_keys, watchlist, review_queue

3. **cameras** (stream management)
   - PK: id
   - FK: region_id (RESTRICT), created_by_user_id (RESTRICT)
   - UK: stream_id
   - Fields: name, source_type (rtsp|http|file|webcam), rtsp_url, status
   - Produces: detections

4. **plates** (detected data)
   - PK: id
   - FK: region_id (RESTRICT)
   - UK: (plate_string_encrypted, region_id) — deduplication per region
   - Fields: plate_string_encrypted (Fernet, app-layer), detected_at, confidence, crop_url
   - Has: detections

5. **detections** (events)
   - PK: id
   - FK: plate_id (CASCADE), camera_id (CASCADE, nullable)
   - Fields: frame_count, avg_confidence, tracking_id (ByteTrack), stream_context (JSON)
   - CHECK: avg_confidence BETWEEN 0 AND 1

6. **audit_log** (append-only, compliance)
   - PK: id
   - FK: user_id (RESTRICT)
   - Fields: action, resource_type, resource_id, details (JSON), ip_addr
   - **Immutable:** No UPDATE/DELETE permissions in migration
   - Used for GDPR/CCPA audit trails

7. **watchlist** (alerts)
   - PK: id
   - FK: region_id (RESTRICT), created_by_user_id (RESTRICT)
   - Fields: plate_pattern (regex), is_active
   - Triggers alerts when plates match

8. **review_queue** (manual review)
   - PK: id
   - FK: reviewed_by_user_id (SET NULL, nullable)
   - Fields: detection_blob (JSON), status (pending|approved|rejected), reviewed_at
   - Queue for uncertain/flagged detections

9. **api_keys** (programmatic auth)
   - PK: id
   - FK: user_id (CASCADE)
   - UK: key_hash (SHA-256, never plaintext)
   - Fields: permissions (JSON scopes), last_used_at, expired_at

### FK Constraints (11 total)
- cameras.region_id → regions.id (RESTRICT)
- cameras.created_by_user_id → users.id (RESTRICT)
- plates.region_id → regions.id (RESTRICT)
- detections.plate_id → plates.id (CASCADE)
- detections.camera_id → cameras.id (CASCADE, nullable)
- audit_log.user_id → users.id (RESTRICT)
- watchlist.region_id → regions.id (RESTRICT)
- watchlist.created_by_user_id → users.id (RESTRICT)
- review_queue.reviewed_by_user_id → users.id (SET NULL)
- api_keys.user_id → users.id (CASCADE)

### Indexes (15 total)
- regions: code (UK lookup)
- users: email (login)
- cameras: region_id, created_by_user_id, stream_id
- plates: (region_id, created_at) — time-range queries, confidence
- detections: plate_id, (camera_id, created_at), tracking_id
- audit_log: user_id, created_at
- watchlist: region_id, created_by_user_id
- review_queue: status, reviewed_by_user_id
- api_keys: user_id

### ORM Implementation
- **Framework:** SQLAlchemy 2.0 with async support (asyncpg backend)
- **Style:** Mapped[] annotations (Python 3.11+), DeclarativeBase
- **Base class:** Base (from db.models.base), TimestampMixin for created_at
- **Relationships:** Declared bidirectionally with back_populates, cascade settings
- **Models location:** db/models/{region,camera,user,plate,detection,audit_log,watchlist,review_queue,api_key}.py

### Migration
- **File:** db/migrations/versions/001_init_schema.py (Alembic)
- **Execution:** `alembic upgrade head` creates all 9 tables in dependency order
- **Downgrade:** Reverse drops in correct order
- **Configuration:** alembic.ini + db/migrations/env.py (Base.metadata autogenerate)

### Security & Compliance
- **Encryption:** Fernet (application-layer) for plate_string_encrypted field
- **Audit logging:** Append-only audit_log table with NO UPDATE/DELETE permissions
- **Access control:** users.role (RBAC base); scoped permissions in api_keys
- **Key storage:** api_keys.key_hash (SHA-256, never plaintext API keys)
- **Data retention:** Forward-compatible structure for region-level retention policies

### Design Rationale
- **Normalization:** Normalized by default (6NF base, with strategic denormalization in stream_context JSON for streaming metadata)
- **Scalability:** Supports 1M+ detections/day via clustering on (region_id, created_at)
- **Constraints:** Deduplication via UK (plate_string_encrypted, region_id) prevents duplicate plates per region
- **Flexibility:** JSON fields (char_confusion_map, stream_context, details, permissions) allow app-layer evolution without schema changes
- **Compliance:** Append-only audit_log + user traceability satisfies GDPR/CCPA audit requirements
