from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SceneEmotion(str, Enum):
    NEUTRAL = "neutral"
    CALM = "calm"
    CONCERN = "concern"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    WHISPER = "whisper"
    ENCOURAGING = "encouraging"
    SERIOUS = "serious"


class RecentMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["USER", "CHARACTER"]
    speaker_id: str | None = Field(default=None, max_length=100)
    content: str = Field(min_length=1, max_length=4000)


class SceneCharacter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    concept: str = Field(min_length=1, max_length=200)
    persona: str = Field(default="", max_length=2000)
    traits: list[str] = Field(default_factory=list, max_length=4)
    speech_style: str = Field(default="", max_length=100)
    relationship_style: str = Field(default="", max_length=100)


class ScenePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_text: str = Field(min_length=1, max_length=4000)
    character_ids: list[str] = Field(min_length=1, max_length=2)
    characters: list[SceneCharacter] = Field(default_factory=list, max_length=2)
    recent_messages: list[RecentMessage] = Field(default_factory=list, max_length=12)

    @field_validator("user_text")
    @classmethod
    def user_text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("user_text must not be blank")
        return value

    @field_validator("character_ids")
    @classmethod
    def character_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        normalized = [character_id.strip() for character_id in value]
        if any(not character_id for character_id in normalized):
            raise ValueError("character_ids must not contain blank values")
        if len(normalized) != len(set(normalized)):
            raise ValueError("character_ids must be unique")
        return normalized

    @field_validator("characters")
    @classmethod
    def characters_must_be_unique(cls, value: list[SceneCharacter]) -> list[SceneCharacter]:
        ids = [character.id for character in value]
        if len(ids) != len(set(ids)):
            raise ValueError("characters must have unique ids")
        return value


class SceneTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speaker_id: str = Field(min_length=1, max_length=100)
    to: str = Field(min_length=1, max_length=100)
    emotion: SceneEmotion
    text: str = Field(min_length=1, max_length=1000)


class ScenePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_action: Literal["CHARACTER_SEQUENCE"]
    turns: list[SceneTurn] = Field(min_length=1, max_length=2)
    return_turn_to: Literal["USER"]
    max_internal_turns: int = Field(ge=0, le=2)

    def validate_speakers(self, allowed_speaker_ids: set[str]) -> None:
        invalid_speakers = {
            turn.speaker_id
            for turn in self.turns
            if turn.speaker_id not in allowed_speaker_ids
        }
        if invalid_speakers:
            raise ValueError("Scene plan contains an unrequested speaker")
        speaker_ids = [turn.speaker_id for turn in self.turns]
        if len(speaker_ids) != len(set(speaker_ids)):
            raise ValueError("A character may speak at most once in a scene plan")
