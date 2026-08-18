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

    content: str = Field(min_length=1, max_length=2000)
    memory_type: str = Field(min_length=1, max_length=24)
    sensitivity: str = Field(min_length=1, max_length=16)


class SpeakerTurnRequest(BaseModel):
    """A single speaker's turn of the Scene Director.

    ``memory_context`` must already be filtered to what ``speaker`` is
    authorized to read (see MemoryRepository.retrieve). No other
    character's private memory is ever placed on this request.
    """

    model_config = ConfigDict(extra="forbid")

    role: Literal["PRIMARY", "SECONDARY"]
    user_text: str = Field(min_length=1, max_length=4000)
    speaker: SceneCharacter
    other_participants: list[SceneCharacter] = Field(
        default_factory=list, max_length=1
    )
    recent_messages: list[RecentMessage] = Field(default_factory=list, max_length=13)
    memory_context: list[MemoryContextItem] = Field(
        default_factory=list, max_length=20
    )


class SpeakerTurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speaker_id: str = Field(min_length=1, max_length=100)
    to: str = Field(min_length=1, max_length=100)
    emotion: SceneEmotion
    text: str = Field(min_length=1, max_length=1000)
    needs_second_speaker: bool = False
    second_speaker_reason: SecondSpeakerReason = SecondSpeakerReason.NONE

    def validate_speaker(self, expected_speaker_id: str) -> None:
        if self.speaker_id != expected_speaker_id:
            raise ValueError("Speaker turn does not match the requested speaker")
