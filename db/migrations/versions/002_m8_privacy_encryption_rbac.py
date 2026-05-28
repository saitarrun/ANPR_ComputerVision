"""M8 Privacy & Security: Field Encryption, Audit Archiving, Multi-Tenant RBAC.

Revision ID: 002
Revises: 001
Create Date: 2026-05-27
"""

from alembic import op
import sqlalchemy as sa


revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add M8 privacy & security schema."""

    # 1. Alter plates.plate_string to use EncryptedString type (String 512).
    op.alter_column(
        "plates",
        "plate_string",
        existing_type=sa.String(255),
        type_=sa.String(512),
        existing_nullable=False,
    )

    # 2. Create user_streams junction table for multi-tenant access.
    op.create_table(
        "user_streams",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("camera_id", sa.String(36), nullable=False),
        sa.Column("permission", sa.String(20), nullable=False, server_default="read"),
        sa.Column("granted_by_user_id", sa.String(36), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", "camera_id", name="uq_user_camera"),
    )
    op.create_index("ix_user_stream_user_id", "user_streams", ["user_id"])
    op.create_index("ix_user_stream_camera_id", "user_streams", ["camera_id"])
    op.create_index("ix_user_stream_permission", "user_streams", ["permission"])

    # 3. Create audit_archives table for S3 export tracking.
    op.create_table(
        "audit_archives",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("s3_key", sa.String(512), nullable=False),
        sa.Column("s3_signature", sa.String(128), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("s3_key", name="uq_audit_archive_s3_key"),
    )
    op.create_index("ix_audit_archive_archived_at", "audit_archives", ["archived_at"])

    # 4. Add region-scoped retention configuration.
    op.add_column("regions", sa.Column("retention_days", sa.Integer(), nullable=False, server_default="90"))
    op.add_column("regions", sa.Column("gdpr_scope", sa.Boolean(), nullable=False, server_default="false"))

    # 5. Add deleted_at soft-delete column to users.
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Rollback M8 changes."""

    op.drop_column("users", "deleted_at")
    op.drop_column("regions", "gdpr_scope")
    op.drop_column("regions", "retention_days")
    op.drop_table("audit_archives")
    op.drop_table("user_streams")

    # Revert plate_string to String(255)
    op.alter_column(
        "plates",
        "plate_string",
        existing_type=sa.String(512),
        type_=sa.String(255),
        existing_nullable=False,
    )
