from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MemoryType = Literal["USER_GLOBAL", "RELATIONSHIP", "GROUP", "CHARACTER_INTERNAL", "PROFILE", "EPISODE"]
Sensitivity = Literal["PUBLIC", "PERSONAL", "PRIVATE", "HIGH"]


class MemoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4000)
    memory_type: MemoryType
    owner_character_id: str | None = Field(default=None, max_length=100)
    sensitivity: Sensitivity = "PERSONAL"
    readable_by_character_ids: list[str] = Field(default_factory=list, max_length=2)
    can_disclose_to: bool = False


class MemoryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    content: str
    memory_type: MemoryType
    sensitivity: Sensitivity
    owner_character_id: str | None
    policy_version: Literal["v1", "v2"] = "v1"
    status: Literal["CANDIDATE", "CONFIRMED", "SUPERSEDED", "REVOKED"] = "CONFIRMED"
    confidence: float = Field(default=1.0, ge=0, le=1)


class MemoryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MemoryRead]


class MemoryShareGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grant_to_character_id: str = Field(min_length=1, max_length=100)
    can_disclose_to: bool = True


class MemoryAccessLogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: UUID
    requesting_character_id: str
    action: str
    decision: str
    reason_code: str
    created_at: str


class MemoryAccessLogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MemoryAccessLogEntry]
