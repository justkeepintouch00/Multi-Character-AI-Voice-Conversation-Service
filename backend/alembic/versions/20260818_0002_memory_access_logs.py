"""Add memory_access_logs for auditing memory ACL decisions.

Revision ID: 20260818_0002
Revises: 20260810_0001
Create Date: 2026-08-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260818_0002"
down_revision: Union[str, None] = "20260810_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "memory_access_logs",
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("memory_id", sa.Uuid(), nullable=False),
        sa.Column("requesting_character_instance_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("decision", sa.String(length=8), nullable=False),
        sa.Column("reason_code", sa.String(length=24), nullable=False),
        sa.Column("scene_plan_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('RETRIEVE', 'DISCLOSE', 'SHARE')",
            name=op.f("ck_memory_access_logs_action_values"),
        ),
        sa.CheckConstraint(
            "decision IN ('ALLOW', 'DENY')",
            name=op.f("ck_memory_access_logs_decision_values"),
        ),
        sa.CheckConstraint(
            "reason_code IN ('OWNER', 'ACL', 'NO_PERMISSION', 'DELETED', 'EXPIRED')",
            name=op.f("ck_memory_access_logs_reason_code_values"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_memory_access_logs_conversation_id_conversations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["memory_id"],
            ["memory_items.id"],
            name=op.f("fk_memory_access_logs_memory_id_memory_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requesting_character_instance_id"],
            ["character_instances.id"],
            name=op.f(
                "fk_memory_access_logs_requesting_character_instance_id_character_instances"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scene_plan_id"],
            ["scene_plans.id"],
            name=op.f("fk_memory_access_logs_scene_plan_id_scene_plans"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_access_logs")),
    )
    op.create_index(
        op.f("ix_memory_access_logs_conversation_id"),
        "memory_access_logs",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_access_logs_memory_id"),
        "memory_access_logs",
        ["memory_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_access_logs_requesting_character_instance_id"),
        "memory_access_logs",
        ["requesting_character_instance_id"],
        unique=False,
    )
    op.create_index(
        "ix_memory_access_logs_memory_requester",
        "memory_access_logs",
        ["memory_id", "requesting_character_instance_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("memory_access_logs")
