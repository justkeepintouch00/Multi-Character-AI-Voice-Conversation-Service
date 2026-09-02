from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ScenarioMode = Literal["A", "B", "C"]
ScenarioStatus = Literal["DRAFT", "PUBLISHED"]


class ScenarioDraftWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ScenarioMode
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=4000)
    opening_guide: str = Field(default="", max_length=4000)
    character_ids: list[str] = Field(min_length=1, max_length=2)
    editor_state: dict[str, Any] = Field(default_factory=dict)
    publish: bool = False

    @model_validator(mode="after")
    def validate_participant_count(self) -> "ScenarioDraftWrite":
        if self.mode in {"A", "B"} and len(self.character_ids) != 1:
            raise ValueError("A·B 모드는 캐릭터를 정확히 1명 선택해야 합니다.")
        if self.mode == "C" and len(self.character_ids) > 2:
            raise ValueError("C 모드는 캐릭터를 최대 2명까지 선택할 수 있습니다.")
        if len(self.character_ids) != len(set(self.character_ids)):
            raise ValueError("같은 캐릭터를 중복 선택할 수 없습니다.")
        return self


class ScenarioDraftRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    mode: ScenarioMode
    title: str
    summary: str
    opening_guide: str
    character_ids: list[str]
    editor_state: dict[str, Any]
    status: ScenarioStatus
