"""Add a versioned optional age to character profiles.

Revision ID: 20260824_0005
Revises: 20260824_0004
Create Date: 2026-08-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260824_0005"
down_revision: Union[str, None] = "20260824_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "character_versions",
        sa.Column("age", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "character_version_age_range",
        "character_versions",
        "age IS NULL OR age BETWEEN 1 AND 999",
    )


def downgrade() -> None:
    op.drop_constraint(
        "character_version_age_range",
        "character_versions",
        type_="check",
    )
    op.drop_column("character_versions", "age")
