"""Core ANPR schema: 6 tables with constraints and indexes.

Revision ID: 001
Revises:
Create Date: 2026-05-27
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create core ANPR tables and indexes."""

    # Create regions table (dimension)
    op.create_table(
        "regions",
        sa.Column("id", sa.Integer(), nullable=False, comment="Region ID"),
        sa.Column(
            "code",
            sa.String(3),
            nullable=False,
            unique=True,
            comment="Region code (IN, EU, US, etc.)",
        ),
        sa.Column(
            "regex",
            sa.String(255),
            nullable=False,
            comment="License plate regex for validation",
        ),
        sa.Column(
            "charset",
            sa.String(255),
            nullable=False,
            comment="Valid characters for region (A-Z0-9, etc.)",
        ),
        sa.Column(
            "retention_days",
            sa.Integer(),
            nullable=False,
            server_default="30",
            comment="Data retention period in days",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="Creation timestamp (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            comment="Last update timestamp (UTC)",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create users table (identity)
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False, comment="User ID"),
        sa.Column(
            "email",
            sa.String(255),
            nullable=False,
            unique=True,
            comment="User email address",
        ),
        sa.Column(
            "username",
            sa.String(255),
            nullable=False,
            unique=True,
            comment="Username",
        ),
        sa.Column(
            "hashed_password",
            sa.String(255),
            nullable=False,
            comment="Bcrypt hashed password",
        ),
        sa.Column(
            "role",
            sa.Enum("viewer", "operator", "admin", name="userrole"),
            nullable=False,
            server_default="viewer",
            comment="User role: viewer, operator, admin",
        ),
        sa.Column(
            "api_key_hash",
            sa.String(255),
            nullable=True,
            comment="API key hash (Phase 1 feature)",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Whether user is active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="Creation timestamp (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            comment="Last update timestamp (UTC)",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create cameras table (dimension)
    op.create_table(
        "cameras",
        sa.Column("id", sa.Integer(), nullable=False, comment="Camera ID"),
        sa.Column(
            "name",
            sa.String(255),
            nullable=False,
            comment="Camera name",
        ),
        sa.Column(
            "source_type",
            sa.String(50),
            nullable=False,
            comment="Source type: webcam, rtsp, iphone, file",
        ),
        sa.Column(
            "stream_url",
            sa.String(1024),
            nullable=True,
            comment="Stream URL (RTSP/HTTP endpoint)",
        ),
        sa.Column(
            "region_id",
            sa.Integer(),
            nullable=False,
            comment="Region ID for this camera",
        ),
        sa.Column(
            "gps_lat",
            sa.Float(),
            nullable=True,
            comment="GPS latitude if available",
        ),
        sa.Column(
            "gps_lon",
            sa.Float(),
            nullable=True,
            comment="GPS longitude if available",
        ),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="inactive",
            comment="Camera status: active, inactive, error",
        ),
        sa.Column(
            "last_heartbeat",
            sa.DateTime(),
            nullable=True,
            comment="Last heartbeat timestamp",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="Creation timestamp (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            comment="Last update timestamp (UTC)",
        ),
        sa.ForeignKeyConstraint(
            ["region_id"],
            ["regions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create plates table (deduplicated fact)
    op.create_table(
        "plates",
        sa.Column("id", sa.Integer(), nullable=False, comment="Plate ID"),
        sa.Column(
            "plate_string",
            sa.String(255),
            nullable=False,
            comment="License plate string (encrypted at rest)",
        ),
        sa.Column(
            "region_id",
            sa.Integer(),
            nullable=False,
            comment="Region ID",
        ),
        sa.Column(
            "detection_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Total detection count for this plate",
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="First detection timestamp",
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            comment="Last detection timestamp",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="Creation timestamp (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            comment="Last update timestamp (UTC)",
        ),
        sa.ForeignKeyConstraint(
            ["region_id"],
            ["regions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plate_string",
            "region_id",
            name="uq_plate_string_region",
        ),
    )

    # Create detections table (immutable fact)
    op.create_table(
        "detections",
        sa.Column("id", sa.Integer(), nullable=False, comment="Detection ID"),
        sa.Column(
            "camera_id",
            sa.Integer(),
            nullable=False,
            comment="Camera ID",
        ),
        sa.Column(
            "plate_id",
            sa.Integer(),
            nullable=False,
            comment="Plate ID",
        ),
        sa.Column(
            "frame_timestamp",
            sa.DateTime(),
            nullable=False,
            comment="Frame capture timestamp",
        ),
        sa.Column(
            "plate_confidence",
            sa.Float(),
            nullable=False,
            comment="Plate detection confidence [0.0, 1.0]",
        ),
        sa.Column(
            "bbox_x1",
            sa.Float(),
            nullable=True,
            comment="Bounding box x1",
        ),
        sa.Column(
            "bbox_y1",
            sa.Float(),
            nullable=True,
            comment="Bounding box y1",
        ),
        sa.Column(
            "bbox_x2",
            sa.Float(),
            nullable=True,
            comment="Bounding box x2",
        ),
        sa.Column(
            "bbox_y2",
            sa.Float(),
            nullable=True,
            comment="Bounding box y2",
        ),
        sa.Column(
            "ocr_backend",
            sa.String(50),
            nullable=True,
            comment="OCR engine used (paddleocr, tesseract, etc.)",
        ),
        sa.Column(
            "quality_score",
            sa.Float(),
            nullable=True,
            comment="Frame quality score (blur, contrast, etc.)",
        ),
        sa.Column(
            "is_persisted",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Whether detection passed quality gate",
        ),
        sa.Column(
            "crop_url",
            sa.String(1024),
            nullable=True,
            comment="S3/MinIO crop image URL",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="Creation timestamp (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            comment="Last update timestamp (UTC)",
        ),
        sa.CheckConstraint(
            "plate_confidence >= 0.0 AND plate_confidence <= 1.0",
            name="ck_detection_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["camera_id"],
            ["cameras.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plate_id"],
            ["plates.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "camera_id",
            "plate_id",
            "frame_timestamp",
            name="uq_detection_dedup",
        ),
    )

    # Create audit_log table (append-only)
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False, comment="Audit log ID"),
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
            comment="User ID who performed the action",
        ),
        sa.Column(
            "action",
            sa.String(50),
            nullable=False,
            comment="Action type: read_plate_detail, create_detection, etc.",
        ),
        sa.Column(
            "resource_type",
            sa.String(50),
            nullable=False,
            comment="Resource type: plate, detection, camera, etc.",
        ),
        sa.Column(
            "resource_id",
            sa.Integer(),
            nullable=True,
            comment="Resource ID being accessed",
        ),
        sa.Column(
            "ip_address",
            sa.String(45),
            nullable=True,
            comment="Client IP address (IPv4 or IPv6)",
        ),
        sa.Column(
            "justification",
            sa.String(1024),
            nullable=True,
            comment="Justification for access (GDPR compliance)",
        ),
        sa.Column(
            "details",
            sa.JSON(),
            nullable=True,
            comment="Additional metadata as JSON",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="Log entry timestamp (UTC)",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    # plates(plate_string) for watchlist match, user search
    op.create_index("ix_plate_string", "plates", ["plate_string"], unique=False)

    # detections(camera_id) for "all detections from camera X"
    op.create_index("ix_detection_camera_id", "detections", ["camera_id"], unique=False)

    # detections(plate_id) for "all occurrences of plate ABC123"
    op.create_index("ix_detection_plate_id", "detections", ["plate_id"], unique=False)

    # detections(frame_timestamp DESC) for time-range queries
    op.create_index(
        "ix_detection_frame_timestamp",
        "detections",
        ["frame_timestamp"],
        unique=False,
        postgresql_desc={"frame_timestamp": True},
    )

    # detections(is_persisted) PARTIAL for valid (persisted) detections
    op.create_index(
        "ix_detection_is_persisted",
        "detections",
        ["is_persisted"],
        unique=False,
        postgresql_where="is_persisted = true",
    )

    # audit_log(created_at DESC) for "last 100 events"
    op.create_index(
        "ix_audit_log_created_at",
        "audit_log",
        ["created_at"],
        unique=False,
        postgresql_desc={"created_at": True},
    )

    # audit_log GIN(details) for "who accessed plate X"
    op.create_index(
        "ix_audit_log_details",
        "audit_log",
        ["details"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Drop core ANPR tables and indexes."""

    # Drop indexes
    op.drop_index("ix_audit_log_details", table_name="audit_log", postgresql_using="gin")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_index("ix_detection_is_persisted", table_name="detections", postgresql_where="is_persisted = true")
    op.drop_index("ix_detection_frame_timestamp", table_name="detections")
    op.drop_index("ix_detection_plate_id", table_name="detections")
    op.drop_index("ix_detection_camera_id", table_name="detections")
    op.drop_index("ix_plate_string", table_name="plates")

    # Drop tables
    op.drop_table("audit_log")
    op.drop_table("detections")
    op.drop_table("plates")
    op.drop_table("cameras")
    op.drop_table("users")
    op.drop_table("regions")
