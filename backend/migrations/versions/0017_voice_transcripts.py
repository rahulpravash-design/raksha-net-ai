"""voice_transcripts

Revision ID: 0017_voice_transcripts
Revises: 0016_mfa_recovery_codes
Create Date: 2026-10-12 17:00:00.000000

Phase 9: what a speech model heard in a reporter's dictation, labelled AI-derived with
its model and confidence, linked to the report it was dictated into. There is no column
for the recording: the audio is never stored.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_voice_transcripts"
down_revision: str | None = "0016_mfa_recovery_codes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "voice_transcripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reporter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reporter_edited", sa.Boolean(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("language", sa.String(length=40), nullable=True),
        sa.Column("language_hint", sa.String(length=8), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("model_version", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("processing_ms", sa.Integer(), nullable=False),
        sa.Column("audio_content_type", sa.String(length=40), nullable=False),
        sa.Column("audio_size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_voice_transcripts_confidence_range"),
        ),
        sa.ForeignKeyConstraint(
            ["reporter_id"],
            ["users.id"],
            name=op.f("fk_voice_transcripts_reporter_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_voice_transcripts_incident_id_incidents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_voice_transcripts")),
        sa.UniqueConstraint("incident_id", name=op.f("uq_voice_transcripts_incident_id")),
    )
    op.create_index(
        op.f("ix_voice_transcripts_reporter_id"),
        "voice_transcripts",
        ["reporter_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_voice_transcripts_reporter_id"), table_name="voice_transcripts")
    op.drop_table("voice_transcripts")
