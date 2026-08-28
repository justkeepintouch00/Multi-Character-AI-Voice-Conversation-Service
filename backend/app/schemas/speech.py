from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.scene_plan import SceneEmotion


class AudioFormat(str, Enum):
    WAV = "wav"
    MP3 = "mp3"


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speaker_id: str = Field(min_length=1, max_length=100)
    voice_id: str | None = Field(default=None, max_length=100)
    text: str = Field(min_length=1, max_length=2000)
    emotion: SceneEmotion = SceneEmotion.NEUTRAL
    emotion_intensity: float = Field(default=1.0, ge=0.0, le=2.0)
    audio_format: AudioFormat = AudioFormat.MP3

    @field_validator("voice_id")
    @classmethod
    def voice_id_must_be_typecast_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if not normalized.startswith(("tc_", "uc_")):
            raise ValueError("voice_id must start with tc_ or uc_")
        return normalized
    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value
class TypecastVoiceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_id: str
    voice_name: str
    gender: str | None = None
    age: str | None = None
    use_cases: list[str] = Field(default_factory=list)
    voice_type: str | None = None

