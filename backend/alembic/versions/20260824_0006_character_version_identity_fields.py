"""Store occupation and gender on each character version.

Revision ID: 20260824_0006
Revises: 20260824_0005
Create Date: 2026-08-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260824_0006"
down_revision: Union[str, None] = "20260824_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "character_versions",
        sa.Column("occupation", sa.String(length=100), server_default="", nullable=False),
    )
    op.add_column(
        "character_versions",
        sa.Column(
            "gender",
            sa.String(length=16),
            server_default="unspecified",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "character_version_gender_values",
        "character_versions",
        "gender IN ('male', 'female', 'unspecified')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "character_version_gender_values",
        "character_versions",
        type_="check",
    )
    op.drop_column("character_versions", "gender")
    op.drop_column("character_versions", "occupation")
