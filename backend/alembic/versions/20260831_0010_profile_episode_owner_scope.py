"""Allow profile and episode memories to be user- or character-scoped.

Revision ID: 20260831_0010
Revises: 20260831_0009
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260831_0010"
down_revision: Union[str, None] = "20260831_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_constraint(expression: str) -> None:
    op.create_check_constraint("owner_matches_memory_type", "memory_items", expression)


def upgrade() -> None:
    op.drop_constraint("owner_matches_memory_type", "memory_items", type_="check")
    _create_constraint(
        "(memory_type IN ('RELATIONSHIP', 'CHARACTER_INTERNAL') AND owner_character_instance_id IS NOT NULL) OR "
        "(memory_type IN ('USER_GLOBAL', 'GROUP') AND owner_character_instance_id IS NULL) OR "
        "memory_type IN ('PROFILE', 'EPISODE')"
    )


def downgrade() -> None:
    op.drop_constraint("owner_matches_memory_type", "memory_items", type_="check")
    _create_constraint(
        "(memory_type IN ('RELATIONSHIP', 'CHARACTER_INTERNAL') AND owner_character_instance_id IS NOT NULL) OR "
        "(memory_type IN ('USER_GLOBAL', 'GROUP') AND owner_character_instance_id IS NULL)"
    )
