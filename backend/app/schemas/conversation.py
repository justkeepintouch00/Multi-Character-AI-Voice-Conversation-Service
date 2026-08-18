from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MemorySharingMode = Literal["NONE", "SHARED", "FIRST_ONLY", "SECOND_ONLY"]


class ConversationOpeningMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speaker_id: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=1000)


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["TALK"] = "TALK"
    character_ids: list[str] = Field(min_length=1, max_length=2)
    opening_message: ConversationOpeningMessage | None = None
    # Only meaningful for 2-character conversations. Governs what read access
    # newly *auto-extracted* memories get, relative to character_ids[0]
    # ("FIRST") and character_ids[1] ("SECOND"). Ignored for 1-character
    # conversations.
    memory_sharing_mode: MemorySharingMode = "NONE"

    @field_validator("character_ids")
    @classmethod
    def character_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        normalized = [character_id.strip() for character_id in value]
        if any(not character_id for character_id in normalized):
            raise ValueError("character_ids must not contain blank values")
        if len(normalized) != len(set(normalized)):
            raise ValueError("character_ids must be unique")
        return normalized

    @model_validator(mode="after")
    def opening_speaker_must_be_a_participant(self) -> "ConversationCreate":
        if (
            self.opening_message is not None
            and self.opening_message.speaker_id not in self.character_ids
        ):
            raise ValueError("opening_message speaker must be a conversation participant")
        return self


class ConversationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    mode: Literal["TALK"]
    status: Literal["ACTIVE", "COMPLETED"]
    character_ids: list[str]
    memory_sharing_mode: MemorySharingMode
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
