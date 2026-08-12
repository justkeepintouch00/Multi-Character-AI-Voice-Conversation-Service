from pydantic import BaseModel, ConfigDict, Field


class TranscriptionSegmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, ge=0)
    text: str
    avg_logprob: float | None = None
    compression_ratio: float | None = Field(default=None, ge=0)
    no_speech_prob: float | None = Field(default=None, ge=0, le=1)


class TranscriptionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    language: str = Field(min_length=2, max_length=10)
    duration_seconds: float | None = Field(default=None, ge=0)
    segments: list[TranscriptionSegmentResponse] | None = None
    model: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    primary_model: str | None = None
    primary_text: str | None = None
    primary_avg_logprob: float | None = None
