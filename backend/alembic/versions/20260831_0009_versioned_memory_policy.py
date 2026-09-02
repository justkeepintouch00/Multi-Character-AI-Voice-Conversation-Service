"""Add versioned memory lifecycle fields for v1/v2 comparisons.

Revision ID: 20260831_0009
Revises: 20260828_0008
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260831_0009"
down_revision: Union[str, None] = "20260828_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "memory_type_values", "memory_items", type_="check"
    )
    op.drop_constraint(
        "owner_matches_memory_type", "memory_items", type_="check"
    )
    op.create_check_constraint(
        "memory_type_values",
        "memory_items",
        "memory_type IN ('USER_GLOBAL', 'RELATIONSHIP', 'GROUP', 'CHARACTER_INTERNAL', 'PROFILE', 'EPISODE')",
    )
    op.create_check_constraint(
        "owner_matches_memory_type",
        "memory_items",
        "(memory_type IN ('RELATIONSHIP', 'CHARACTER_INTERNAL') AND owner_character_instance_id IS NOT NULL) OR (memory_type IN ('USER_GLOBAL', 'GROUP') AND owner_character_instance_id IS NULL) OR memory_type IN ('PROFILE', 'EPISODE')",
    )
    op.add_column(
        "memory_items",
        sa.Column("policy_version", sa.String(length=8), nullable=False, server_default="v1"),
    )
    op.add_column(
        "memory_items",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="CONFIRMED"),
    )
    op.add_column(
        "memory_items",
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False, server_default="1.0"),
    )
    op.add_column("memory_items", sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("memory_items", sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True))
    op.add_column("memory_items", sa.Column("supersedes_memory_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_memory_items_supersedes_memory_id_memory_items",
        "memory_items",
        "memory_items",
        ["supersedes_memory_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_memory_items_supersedes_memory_id", "memory_items", ["supersedes_memory_id"])
    op.create_index("ix_memory_items_user_policy", "memory_items", ["user_id", "policy_version"])
    op.create_check_constraint("policy_version_values", "memory_items", "policy_version IN ('v1', 'v2')")
    op.create_check_constraint("memory_status_values", "memory_items", "status IN ('CANDIDATE', 'CONFIRMED', 'SUPERSEDED', 'REVOKED')")
    op.create_check_constraint("confidence_range", "memory_items", "confidence >= 0 AND confidence <= 1")

    op.add_column("memory_graph_edges", sa.Column("policy_version", sa.String(length=8), nullable=False, server_default="v1"))
    op.add_column("memory_graph_edges", sa.Column("status", sa.String(length=16), nullable=False, server_default="CONFIRMED"))
    op.add_column("memory_graph_edges", sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False, server_default="1.0"))
    op.add_column("memory_graph_edges", sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("memory_graph_edges", sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True))
    op.add_column("memory_graph_edges", sa.Column("supersedes_edge_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_memory_graph_edges_supersedes_edge_id_memory_graph_edges",
        "memory_graph_edges",
        "memory_graph_edges",
        ["supersedes_edge_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_memory_graph_edges_supersedes_edge_id", "memory_graph_edges", ["supersedes_edge_id"])
    op.create_index("ix_memory_graph_edges_user_policy", "memory_graph_edges", ["user_id", "policy_version"])
    op.create_check_constraint("policy_version_values", "memory_graph_edges", "policy_version IN ('v1', 'v2')")
    op.create_check_constraint("edge_status_values", "memory_graph_edges", "status IN ('CANDIDATE', 'CONFIRMED', 'SUPERSEDED', 'REVOKED')")
    op.create_check_constraint("edge_confidence_range", "memory_graph_edges", "confidence >= 0 AND confidence <= 1")


def downgrade() -> None:
    for name in ("edge_confidence_range", "edge_status_values", "policy_version_values"):
        op.drop_constraint(name, "memory_graph_edges", type_="check")
    op.drop_index("ix_memory_graph_edges_user_policy", table_name="memory_graph_edges")
    op.drop_index("ix_memory_graph_edges_supersedes_edge_id", table_name="memory_graph_edges")
    op.drop_constraint("fk_memory_graph_edges_supersedes_edge_id_memory_graph_edges", "memory_graph_edges", type_="foreignkey")
    for column in ("supersedes_edge_id", "valid_to", "valid_from", "confidence", "status", "policy_version"):
        op.drop_column("memory_graph_edges", column)

    for name in ("confidence_range", "memory_status_values", "policy_version_values"):
        op.drop_constraint(name, "memory_items", type_="check")
    op.drop_index("ix_memory_items_user_policy", table_name="memory_items")
    op.drop_index("ix_memory_items_supersedes_memory_id", table_name="memory_items")
    op.drop_constraint("fk_memory_items_supersedes_memory_id_memory_items", "memory_items", type_="foreignkey")
    for column in ("supersedes_memory_id", "valid_to", "valid_from", "confidence", "status", "policy_version"):
        op.drop_column("memory_items", column)
    op.drop_constraint("owner_matches_memory_type", "memory_items", type_="check")
    op.drop_constraint("memory_type_values", "memory_items", type_="check")
    op.create_check_constraint(
        "memory_type_values", "memory_items",
        "memory_type IN ('USER_GLOBAL', 'RELATIONSHIP', 'GROUP', 'CHARACTER_INTERNAL')",
    )
    op.create_check_constraint(
        "owner_matches_memory_type", "memory_items",
        "(memory_type IN ('RELATIONSHIP', 'CHARACTER_INTERNAL') AND owner_character_instance_id IS NOT NULL) OR (memory_type IN ('USER_GLOBAL', 'GROUP') AND owner_character_instance_id IS NULL)",
    )
