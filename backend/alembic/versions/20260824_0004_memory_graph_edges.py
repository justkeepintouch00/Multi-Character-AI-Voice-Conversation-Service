"""Add ACL-scoped memory graph edges for partial GraphRAG.

Revision ID: 20260824_0004
Revises: 20260818_0003
Create Date: 2026-08-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260824_0004"
down_revision: Union[str, None] = "20260818_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "memory_graph_edges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("memory_id", sa.Uuid(), nullable=False),
        sa.Column("source_entity", sa.String(length=160), nullable=False),
        sa.Column("relation", sa.String(length=80), nullable=False),
        sa.Column("target_entity", sa.String(length=160), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.CheckConstraint("length(trim(source_entity)) > 0", name="nonempty_source_entity"),
        sa.CheckConstraint("length(trim(relation)) > 0", name="nonempty_relation"),
        sa.CheckConstraint("length(trim(target_entity)) > 0", name="nonempty_target_entity"),
        sa.ForeignKeyConstraint(["memory_id"], ["memory_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("memory_id", "source_entity", "relation", "target_entity"),
    )
    op.create_index("ix_memory_graph_edges_user_source", "memory_graph_edges", ["user_id", "source_entity"])
    op.create_index("ix_memory_graph_edges_user_target", "memory_graph_edges", ["user_id", "target_entity"])
    op.create_index("ix_memory_graph_edges_memory", "memory_graph_edges", ["memory_id"])


def downgrade() -> None:
    op.drop_index("ix_memory_graph_edges_memory", table_name="memory_graph_edges")
    op.drop_index("ix_memory_graph_edges_user_target", table_name="memory_graph_edges")
    op.drop_index("ix_memory_graph_edges_user_source", table_name="memory_graph_edges")
    op.drop_table("memory_graph_edges")

