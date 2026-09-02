"""Store additional character prompt on each character version.

Revision ID: 20260824_0007
Revises: 20260824_0006
Create Date: 2026-08-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260824_0007"
down_revision: Union[str, None] = "20260824_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "character_versions",
        sa.Column(
            "additional_character_prompt",
            sa.Text(),
            server_default="",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("character_versions", "additional_character_prompt")
