from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from app.schemas.scene_plan import ScenePlan, ScenePlanRequest
from app.schemas.speech import SpeechRequest


class ProviderError(RuntimeError):
    """Base error that is safe to translate at the API boundary."""

    provider: str

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(message)
        self.provider = provider


class ProviderConfigurationError(ProviderError):
    pass


class ProviderInputError(ProviderError):
    pass


class ProviderRequestError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class ProviderResponseError(ProviderError):
    pass


@dataclass(frozen=True, slots=True)
class TranscriptionSegment:
    id: int | None
    start_seconds: float | None
    end_seconds: float | None
    text: str
    avg_logprob: float | None
    compression_ratio: float | None
    no_speech_prob: float | None


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    text: str
    language: str
    duration_seconds: float | None = None
    segments: tuple[TranscriptionSegment, ...] = ()
    model: str | None = None
    fallback_used: bool = False
    primary_model: str | None = None
    primary_text: str | None = None
    primary_avg_logprob: float | None = None


@dataclass(frozen=True, slots=True)
class AudioStream:
    chunks: AsyncIterator[bytes]
    media_type: str


class SceneDirectorProvider(Protocol):
    async def create_scene_plan(self, request: ScenePlanRequest) -> ScenePlan: ...


class STTProvider(Protocol):
    async def transcribe(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str,
        language: str,
    ) -> TranscriptionResult: ...


class TTSProvider(Protocol):
    async def stream_speech(self, request: SpeechRequest) -> AudioStream: ...
