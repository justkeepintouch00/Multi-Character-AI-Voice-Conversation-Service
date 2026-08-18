from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin


EMPTY_JSON = text("'{}'::jsonb")


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    external_auth_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )


class Asset(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('IMAGE', 'AUDIO', 'BACKGROUND', 'PROP', 'EVENT', 'ENDING')",
            name="asset_type_values",
        ),
    )

    owner_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    asset_type: Mapped[str] = mapped_column(String(24), nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=EMPTY_JSON, nullable=False
    )


class CharacterTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "character_templates"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('PRIVATE', 'UNLISTED', 'PUBLIC')",
            name="visibility_values",
        ),
    )

    creator_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    visibility: Mapped[str] = mapped_column(
        String(16), default="PRIVATE", server_default="PRIVATE", nullable=False
    )
    current_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "character_versions.id",
            name="fk_character_templates_current_version_id",
            use_alter=True,
            ondelete="SET NULL",
        ),
        nullable=True,
    )


class CharacterVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "character_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "version"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint(
            "char_length(concept_prompt) BETWEEN 50 AND 200",
            name="concept_prompt_length",
        ),
    )

    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("character_templates.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    concept_prompt: Mapped[str] = mapped_column(String(200), nullable=False)
    traits_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=EMPTY_JSON, nullable=False
    )
    speech_style_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=EMPTY_JSON, nullable=False
    )
    relationship_defaults_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=EMPTY_JSON, nullable=False
    )
    additional_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)


class VoiceProfile(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "voice_profiles"

    character_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("character_versions.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    provider_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_voice_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    style_defaults_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=EMPTY_JSON, nullable=False
    )
    sample_asset_uri: Mapped[str | None] = mapped_column(Text, nullable=True)


class MotionProfile(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "motion_profiles"

    character_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("character_versions.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    motion_map_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=EMPTY_JSON, nullable=False
    )
    renderer_config_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=EMPTY_JSON, nullable=False
    )


class CharacterInstance(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "character_instances"
    __table_args__ = (
        UniqueConstraint("user_id", "template_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("character_templates.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("character_versions.id", ondelete="RESTRICT"), index=True
    )
    nickname_override: Mapped[str | None] = mapped_column(String(100), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CharacterRelationship(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "character_relationships"
    __table_args__ = (
        UniqueConstraint("user_id", "character_instance_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    character_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("character_instances.id", ondelete="CASCADE"), index=True
    )
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False)
    closeness: Mapped[float] = mapped_column(
        Numeric(6, 3), default=0, server_default="0", nullable=False
    )
    state_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=EMPTY_JSON, nullable=False
    )


class AdaptationProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "adaptation_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "character_instance_id"),
        CheckConstraint(
            "supporting_session_count >= 0", name="nonnegative_session_count"
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    character_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("character_instances.id", ondelete="CASCADE"), index=True
    )
    preferences_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=EMPTY_JSON, nullable=False
    )
    supporting_session_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )


class CharacterAsset(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "character_assets"
    __table_args__ = (
        UniqueConstraint("character_template_id", "asset_id", "asset_role"),
    )

    character_template_id: Mapped[UUID] = mapped_column(
        ForeignKey("character_templates.id", ondelete="CASCADE"), index=True
    )
    character_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("character_versions.id", ondelete="CASCADE"), nullable=True
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), index=True
    )
    asset_role: Mapped[str] = mapped_column(String(50), nullable=False)
    display_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )


class Scenario(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scenarios"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('PRACTICE', 'SCENARIO', 'TALK')", name="mode_values"
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="status_values"
        ),
        CheckConstraint("schema_version > 0", name="positive_schema_version"),
    )

    creator_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="DRAFT", server_default="DRAFT", nullable=False
    )
    schema_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )


class ScenarioCharacter(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "scenario_characters"
    __table_args__ = (
        UniqueConstraint(
            "scenario_id", "display_order", name="uq_scenario_characters_order"
        ),
        UniqueConstraint(
            "scenario_id",
            "character_template_id",
            name="uq_scenario_characters_template",
        ),
    )

    scenario_id: Mapped[UUID] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    character_template_id: Mapped[UUID] = mapped_column(
        ForeignKey("character_templates.id", ondelete="RESTRICT"), index=True
    )
    scenario_role: Mapped[str] = mapped_column(String(100), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)


class ScenarioScene(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "scenario_scenes"
    __table_args__ = (
        UniqueConstraint("scenario_id", "sequence"),
        CheckConstraint("sequence >= 0", name="nonnegative_sequence"),
    )

    scenario_id: Mapped[UUID] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    background_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    scene_config_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=EMPTY_JSON, nullable=False
    )


class ScenarioTurn(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "scenario_turns"
    __table_args__ = (
        UniqueConstraint("scene_id", "sequence"),
        CheckConstraint("sequence >= 0", name="nonnegative_sequence"),
        CheckConstraint(
            "user_input_type IN ('VOICE', 'TEXT', 'CHOICE', 'NONE')",
            name="user_input_type_values",
        ),
    )

    scene_id: Mapped[UUID] = mapped_column(
        ForeignKey("scenario_scenes.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    scenario_character_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("scenario_characters.id", ondelete="SET NULL"), nullable=True
    )
    screen_description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    character_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_input_type: Mapped[str] = mapped_column(String(16), nullable=False)
    evaluation_rule_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=EMPTY_JSON, nullable=False
    )
    branch_rule_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=EMPTY_JSON, nullable=False
    )
    image_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )


class ScenarioEnding(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "scenario_endings"
    __table_args__ = (
        UniqueConstraint("scenario_id", "title"),
    )

    scenario_id: Mapped[UUID] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    condition_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=EMPTY_JSON, nullable=False
    )
    ending_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('PRACTICE', 'SCENARIO', 'TALK')", name="mode_values"
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'PROCESSING', 'COMPLETED', 'CANCELLED', 'ARCHIVED')",
            name="status_values",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    scenario_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("scenarios.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), default="ACTIVE", server_default="ACTIVE", nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"
    __table_args__ = (
        UniqueConstraint("conversation_id", "display_order"),
        CheckConstraint("display_order >= 0", name="nonnegative_display_order"),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    character_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("character_instances.id", ondelete="CASCADE"), primary_key=True
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    participant_role: Mapped[str] = mapped_column(
        String(50), default="ACTIVE", server_default="ACTIVE", nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    left_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Message(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "speaker_type IN ('USER', 'CHARACTER', 'SYSTEM')",
            name="speaker_type_values",
        ),
        CheckConstraint(
            "input_mode IN ('TEXT', 'VOICE', 'SYSTEM')", name="input_mode_values"
        ),
        CheckConstraint(
            "(speaker_type = 'USER' AND speaker_user_id IS NOT NULL "
            "AND speaker_character_instance_id IS NULL) OR "
            "(speaker_type = 'CHARACTER' AND speaker_user_id IS NULL "
            "AND speaker_character_instance_id IS NOT NULL) OR "
            "(speaker_type = 'SYSTEM' AND speaker_user_id IS NULL "
            "AND speaker_character_instance_id IS NULL)",
            name="speaker_reference_matches_type",
        ),
        CheckConstraint(
            "scene_turn_index IS NULL OR scene_turn_index >= 0",
            name="nonnegative_scene_turn_index",
        ),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    speaker_type: Mapped[str] = mapped_column(String(16), nullable=False)
    speaker_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    speaker_character_instance_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("character_instances.id", ondelete="SET NULL"), nullable=True
    )
    scene_plan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "scene_plans.id",
            name="fk_messages_scene_plan_id",
            use_alter=True,
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    scene_turn_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    input_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    finalized: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    interrupted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )


class ScenePlan(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "scene_plans"
    __table_args__ = (
        CheckConstraint(
            "internal_step_count BETWEEN 0 AND 5", name="internal_step_limit"
        ),
        CheckConstraint(
            "visible_turn_count BETWEEN 0 AND 2", name="visible_turn_limit"
        ),
        CheckConstraint(
            "return_turn_to IN ('USER', 'SYSTEM')", name="return_turn_values"
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    triggering_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    can_ai_speak: Mapped[bool] = mapped_column(Boolean, nullable=False)
    internal_step_count: Mapped[int] = mapped_column(Integer, nullable=False)
    visible_turn_count: Mapped[int] = mapped_column(Integer, nullable=False)
    return_turn_to: Mapped[str] = mapped_column(
        String(16), default="USER", server_default="USER", nullable=False
    )
    plan_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class MessageSegment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "message_segments"
    __table_args__ = (
        UniqueConstraint("message_id", "sequence"),
        CheckConstraint("sequence >= 0", name="nonnegative_sequence"),
        CheckConstraint("played_ms >= 0", name="nonnegative_played_ms"),
        CheckConstraint(
            "audio_status IN ('GENERATED', 'QUEUED', 'PLAYING', 'PLAYED', "
            "'DISCARDED', 'CANCELLED')",
            name="audio_status_values",
        ),
    )

    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    audio_status: Mapped[str] = mapped_column(String(16), nullable=False)
    played_ms: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    provider_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audio_storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)


class Job(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key"),
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'REVIEWING', 'COMPLETED', "
            "'RETRYING', 'FAILED', 'CANCELLED')",
            name="status_values",
        ),
        CheckConstraint("attempt >= 0", name="nonnegative_attempt"),
        Index("ix_jobs_status_created", "status", "created_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    request_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    result_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="QUEUED", server_default="QUEUED", nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    attempt: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class JobCheckpoint(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "job_checkpoints"
    __table_args__ = (
        UniqueConstraint("job_id", "step"),
    )

    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=EMPTY_JSON, nullable=False
    )


class MemoryItem(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "memory_items"
    __table_args__ = (
        CheckConstraint(
            "memory_type IN ('USER_GLOBAL', 'RELATIONSHIP', 'GROUP', "
            "'CHARACTER_INTERNAL')",
            name="memory_type_values",
        ),
        CheckConstraint(
            "sensitivity IN ('PUBLIC', 'PERSONAL', 'PRIVATE', 'HIGH')",
            name="sensitivity_values",
        ),
        CheckConstraint(
            "(memory_type IN ('RELATIONSHIP', 'CHARACTER_INTERNAL') "
            "AND owner_character_instance_id IS NOT NULL) OR "
            "(memory_type IN ('USER_GLOBAL', 'GROUP') "
            "AND owner_character_instance_id IS NULL)",
            name="owner_matches_memory_type",
        ),
        Index("ix_memory_items_user_type", "user_id", "memory_type"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    memory_type: Mapped[str] = mapped_column(String(24), nullable=False)
    owner_character_instance_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("character_instances.id", ondelete="CASCADE"), nullable=True
    )
    source_conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sensitivity: Mapped[str] = mapped_column(
        String(16), default="PERSONAL", server_default="PERSONAL", nullable=False
    )
    # Kept provider-neutral until the embedding model/dimension is confirmed.
    # A later migration can change JSONB to pgvector without renaming the column.
    embedding: Mapped[list[float] | None] = mapped_column(JSONB, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=EMPTY_JSON, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MemoryACL(Base):
    __tablename__ = "memory_acl"
    __table_args__ = (
        CheckConstraint(
            "subject_type IN ('USER', 'CHARACTER_INSTANCE')",
            name="subject_type_values",
        ),
        CheckConstraint(
            "(NOT can_read OR can_know) AND (NOT can_disclose_to OR can_know)",
            name="permission_implications",
        ),
        Index("ix_memory_acl_subject", "subject_type", "subject_id"),
    )

    memory_id: Mapped[UUID] = mapped_column(
        ForeignKey("memory_items.id", ondelete="CASCADE"), primary_key=True
    )
    subject_type: Mapped[str] = mapped_column(
        String(24), primary_key=True
    )
    subject_id: Mapped[UUID] = mapped_column(primary_key=True)
    can_know: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    can_read: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    can_disclose_to: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    granted_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )


class MemorySource(Base):
    __tablename__ = "memory_sources"

    memory_id: Mapped[UUID] = mapped_column(
        ForeignKey("memory_items.id", ondelete="CASCADE"), primary_key=True
    )
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )


class MemoryAccessLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "memory_access_logs"
    __table_args__ = (
        CheckConstraint(
            "action IN ('RETRIEVE', 'DISCLOSE', 'SHARE')", name="action_values"
        ),
        CheckConstraint("decision IN ('ALLOW', 'DENY')", name="decision_values"),
        CheckConstraint(
            "reason_code IN ('OWNER', 'ACL', 'NO_PERMISSION', 'DELETED', 'EXPIRED')",
            name="reason_code_values",
        ),
        Index(
            "ix_memory_access_logs_memory_requester",
            "memory_id",
            "requesting_character_instance_id",
        ),
    )

    conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    memory_id: Mapped[UUID] = mapped_column(
        ForeignKey("memory_items.id", ondelete="CASCADE"), index=True
    )
    requesting_character_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("character_instances.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    decision: Mapped[str] = mapped_column(String(8), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(24), nullable=False)
    scene_plan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("scene_plans.id", ondelete="SET NULL"), nullable=True
    )


class ScenarioRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "scenario_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'CANCELLED')", name="status_values"
        ),
    )

    scenario_id: Mapped[UUID] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), unique=True
    )
    ending_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("scenario_endings.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), default="RUNNING", server_default="RUNNING", nullable=False
    )
    state_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=EMPTY_JSON, nullable=False
    )
    result_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=EMPTY_JSON, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EvaluationItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "evaluation_items"
    __table_args__ = (
        CheckConstraint(
            "feedback_type IN ('DID_WELL', 'TO_IMPROVE')",
            name="feedback_type_values",
        ),
        UniqueConstraint("scenario_run_id", "display_order"),
    )

    scenario_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("scenario_runs.id", ondelete="CASCADE"), index=True
    )
    feedback_type: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)


__all__ = [
    "AdaptationProfile",
    "Asset",
    "CharacterAsset",
    "CharacterInstance",
    "CharacterRelationship",
    "CharacterTemplate",
    "CharacterVersion",
    "Conversation",
    "ConversationParticipant",
    "EvaluationItem",
    "Job",
    "JobCheckpoint",
    "MemoryACL",
    "MemoryAccessLog",
    "MemoryItem",
    "MemorySource",
    "Message",
    "MessageSegment",
    "MotionProfile",
    "Scenario",
    "ScenarioCharacter",
    "ScenarioEnding",
    "ScenarioRun",
    "ScenarioScene",
    "ScenarioTurn",
    "ScenePlan",
    "User",
    "VoiceProfile",
]
