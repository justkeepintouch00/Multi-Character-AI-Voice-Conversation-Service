from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.scene_plan import RecentMessage, SceneCharacter, SceneEmotion


class SecondSpeakerReason(str, Enum):
    NONE = "NONE"
    DIFFERING_VIEWPOINT = "DIFFERING_VIEWPOINT"
    AGREEMENT_BACKUP = "AGREEMENT_BACKUP"


class MemoryContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=2000)
    memory_type: str = Field(min_length=1, max_length=24)
    sensitivity: str = Field(min_length=1, max_length=16)


class MemoryGraphRelation(BaseModel):
    """One optional, user-grounded relation edge extracted with a memory."""

    model_config = ConfigDict(extra="forbid")

    has_relation: bool = False
    source_entity: str = Field(default="", max_length=160)
    relation: str = Field(default="", max_length=80)
    target_entity: str = Field(default="", max_length=160)
    summary: str = Field(default="", max_length=300)


class ExtractedMemory(BaseModel):
    """A candidate long-term fact the speaker noticed in this turn.

    ``has_memory`` is always present so the schema stays a plain required
    object (no optional/nullable branch) even when there's nothing worth
    keeping -- the caller only acts on it when has_memory is true.
    """

    model_config = ConfigDict(extra="forbid")

    has_memory: bool
    content: str = Field(default="", max_length=500)
    sensitivity: Literal["PUBLIC", "PERSONAL", "PRIVATE", "HIGH"] = "PERSONAL"
    graph_relation: MemoryGraphRelation = Field(default_factory=MemoryGraphRelation)


class SpeakerTurnRequest(BaseModel):
    """A single speaker's turn of the Scene Director.

    ``memory_context`` must already be filtered to what ``speaker`` is
    authorized to read (see MemoryRepository.retrieve). No other
    character's private memory is ever placed on this request.
    """

    model_config = ConfigDict(extra="forbid")

    role: Literal["PRIMARY", "SECONDARY"]
    user_text: str = Field(min_length=1, max_length=4000)
    user_display_name: str | None = Field(default=None, max_length=100)
    speaker: SceneCharacter
    other_participants: list[SceneCharacter] = Field(
        default_factory=list, max_length=1
    )
    recent_messages: list[RecentMessage] = Field(default_factory=list, max_length=13)
    memory_context: list[MemoryContextItem] = Field(
        default_factory=list, max_length=20
    )
    # Service-level routing facts are passed separately from the user's text.
    # This lets the provider distinguish an explicit dual-speaker request
    # without exposing any private memory.
    turn_instruction: str | None = Field(default=None, max_length=500)


class SpeakerTurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speaker_id: str = Field(min_length=1, max_length=100)
    to: str = Field(min_length=1, max_length=100)
    emotion: SceneEmotion
    text: str = Field(min_length=1, max_length=1000)
    needs_second_speaker: bool = False
    second_speaker_reason: SecondSpeakerReason = SecondSpeakerReason.NONE
    extracted_memory: ExtractedMemory = Field(default_factory=lambda: ExtractedMemory(has_memory=False))
    # ids from *this speaker's own* memory_context that they just voiced
    # aloud to the other participant. Never mutates DB access by itself --
    # see ShareSuggestion in schemas/message.py.
    disclosed_memory_ids: list[str] = Field(default_factory=list, max_length=5)

    def validate_speaker(self, expected_speaker_id: str) -> None:
        if self.speaker_id != expected_speaker_id:
            raise ValueError("Speaker turn does not match the requested speaker")
