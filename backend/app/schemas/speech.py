from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.scene_plan import SceneEmotion


class AudioFormat(str, Enum):
    WAV = "wav"
    MP3 = "mp3"


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speaker_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=2000)
    emotion: SceneEmotion = SceneEmotion.NEUTRAL
    emotion_intensity: float = Field(default=1.0, ge=0.0, le=2.0)
    audio_format: AudioFormat = AudioFormat.MP3

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value
