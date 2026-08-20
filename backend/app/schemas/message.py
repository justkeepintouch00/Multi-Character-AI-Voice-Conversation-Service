from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.scene_plan import ScenePlan


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4000)
    input_mode: Literal["TEXT", "VOICE"] = "TEXT"

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value


class MessageRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    speaker_type: Literal["USER", "CHARACTER", "SYSTEM"]
    speaker_id: str | None
    content: str
    input_mode: Literal["TEXT", "VOICE", "SYSTEM"]
    finalized: bool
    interrupted: bool
    created_at: datetime


class MessageListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MessageRead]


class ShareSuggestion(BaseModel):
    """A character voiced another character's private memory out loud.

    This never changes DB access on its own -- speaking something aloud in
    one turn doesn't grant permanent read access. It's surfaced so the user
    can explicitly approve turning it into a real ACL grant via
    POST /api/v1/memories/{memory_id}/share.
    """

    model_config = ConfigDict(extra="forbid")

    memory_id: UUID
    from_character_id: str
    to_character_id: str
    content_preview: str


class MessageExchangeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_message: MessageRead
    scene_plan: ScenePlan
    assistant_messages: list[MessageRead]
    share_suggestions: list[ShareSuggestion] = Field(default_factory=list)
