from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CharacterWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    nickname: str | None = Field(default=None, max_length=100)
    age: int | None = Field(default=None, ge=1, le=999)
    occupation: str = Field(default="", max_length=100)
    gender: Literal["male", "female", "unspecified"] = "unspecified"
    concept: str = Field(min_length=50, max_length=200)
    persona: str = Field(default="", max_length=2000)
    additional_prompt: str = Field(default="", max_length=500)
    traits: list[str] = Field(min_length=1, max_length=4)
    speech_style: str = Field(default="관계에 따라 변화", max_length=100)
    response_length: str = Field(default="보통", max_length=50)
    relationship_style: str = Field(default="편한 친구", max_length=100)
    voice_label: str = Field(default="", max_length=100)
    typecast_voice_id: str | None = Field(default=None, max_length=100)

    @field_validator(
        "name", "occupation", "concept", "persona", "additional_prompt", "speech_style", "voice_label"
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("nickname")
    @classmethod
    def normalize_nickname(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("traits")
    @classmethod
    def normalize_traits(cls, value: list[str]) -> list[str]:
        normalized = [trait.strip() for trait in value]
        if any(not trait for trait in normalized):
            raise ValueError("traits must not contain blank values")
        if len(normalized) != len(set(normalized)):
            raise ValueError("traits must be unique")
        return normalized


    @field_validator("typecast_voice_id")
    @classmethod
    def normalize_typecast_voice_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if not normalized.startswith(("tc_", "uc_")):
            raise ValueError("typecast_voice_id must start with tc_ or uc_")
        return normalized
class CharacterRead(CharacterWrite):
    id: str
    version: int
    image_url: str | None = Field(default=None, max_length=500)


class CharacterListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CharacterRead]


