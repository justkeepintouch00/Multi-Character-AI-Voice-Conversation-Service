"""Add memory_sharing_mode to conversations.

Revision ID: 20260818_0003
Revises: 20260818_0002
Create Date: 2026-08-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260818_0003"
down_revision: Union[str, None] = "20260818_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "memory_sharing_mode",
            sa.String(length=16),
            server_default="NONE",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_conversations_memory_sharing_mode_values"),
        "conversations",
        "memory_sharing_mode IN ('NONE', 'SHARED', 'FIRST_ONLY', 'SECOND_ONLY')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_conversations_memory_sharing_mode_values"),
        "conversations",
        type_="check",
    )
    op.drop_column("conversations", "memory_sharing_mode")
