from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    age: int | None = Field(default=None, ge=1, le=999)
    age_group: str = Field(default="", max_length=40)
    occupation: str = Field(default="", max_length=100)
    gender: str = Field(default="unspecified", max_length=16)
    concept: str = Field(min_length=1, max_length=200)
    persona: str = Field(default="", max_length=2600)
    traits: list[str] = Field(default_factory=list, max_length=4)
    speech_style: str = Field(default="", max_length=100)
    relationship_style: str = Field(default="", max_length=100)


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
