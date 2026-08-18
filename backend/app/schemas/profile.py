from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProfileRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("display_name must not be blank")
        return value
