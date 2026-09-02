from sqlalchemy import CheckConstraint, UniqueConstraint

from app.db import models  # noqa: F401 - register mappings
from app.db.base import Base


EXPECTED_TABLES = {
    "users",
    "assets",
    "character_templates",
    "character_versions",
    "character_instances",
    "character_relationships",
    "adaptation_profiles",
    "voice_profiles",
    "motion_profiles",
    "character_assets",
    "conversations",
    "conversation_participants",
    "messages",
    "message_segments",
    "scene_plans",
    "jobs",
    "job_checkpoints",
    "memory_items",
    "memory_acl",
    "memory_sources",
    "memory_graph_edges",
    "memory_access_logs",
    "scenarios",
    "scenario_characters",
    "scenario_scenes",
    "scenario_turns",
    "scenario_endings",
    "scenario_runs",
    "evaluation_items",
}


def check_sql(table_name: str) -> str:
    table = Base.metadata.tables[table_name]
    return " ".join(
        str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    )


def unique_column_sets(table_name: str) -> set[tuple[str, ...]]:
    table = Base.metadata.tables[table_name]
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_all_erd_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_scene_director_limits_are_database_constraints() -> None:
    sql = check_sql("scene_plans")
    assert "internal_step_count BETWEEN 0 AND 5" in sql
    assert "visible_turn_count BETWEEN 0 AND 2" in sql


def test_memory_acl_separates_read_and_disclosure() -> None:
    columns = Base.metadata.tables["memory_acl"].columns
    assert "can_know" in columns
    assert "can_read" in columns
    assert "can_disclose_to" in columns


def test_memory_access_log_records_decision_and_reason() -> None:
    sql = check_sql("memory_access_logs")
    assert "decision IN ('ALLOW', 'DENY')" in sql
    assert "'OWNER'" in sql and "'NO_PERMISSION'" in sql


def test_conversation_participant_is_unique_per_character() -> None:
    table = Base.metadata.tables["conversation_participants"]
    assert tuple(column.name for column in table.primary_key.columns) == (
        "conversation_id",
        "character_instance_id",
    )


def test_scenario_character_constraints_have_distinct_names() -> None:
    table = Base.metadata.tables["scenario_characters"]
    names = [
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    assert len(names) == len(set(names))
    assert unique_column_sets("scenario_characters") == {
        ("scenario_id", "display_order"),
        ("scenario_id", "character_template_id"),
    }

