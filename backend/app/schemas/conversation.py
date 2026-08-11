from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["TALK"] = "TALK"
    character_ids: list[str] = Field(min_length=1, max_length=2)

    @field_validator("character_ids")
    @classmethod
    def character_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        normalized = [character_id.strip() for character_id in value]
        if any(not character_id for character_id in normalized):
            raise ValueError("character_ids must not contain blank values")
        if len(normalized) != len(set(normalized)):
            raise ValueError("character_ids must be unique")
        return normalized


class ConversationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    mode: Literal["TALK"]
    status: Literal["ACTIVE", "COMPLETED"]
    character_ids: list[str]
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
