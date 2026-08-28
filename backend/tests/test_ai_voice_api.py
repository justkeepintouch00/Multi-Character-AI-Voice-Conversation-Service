from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_scene_director_provider,
    get_stt_provider,
    get_tts_provider,
)
from app.main import app
from app.providers.base import (
    AudioStream,
    ProviderConfigurationError,
    ProviderRequestError,
    TranscriptionResult,
)
from app.schemas.speaker_turn import SpeakerTurnRequest, SpeakerTurnResult
from app.schemas.speech import SpeechRequest


client = TestClient(app)


class FakeSceneDirector:
    async def create_speaker_turn(
        self, request: SpeakerTurnRequest
    ) -> SpeakerTurnResult:
        return SpeakerTurnResult(
            speaker_id=request.speaker.id,
            to="USER",
            emotion="concern",
            text="많이 지쳤겠네. 천천히 말해도 괜찮아.",
        )


class FakeSTT:
    async def transcribe(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str,
        language: str,
    ) -> TranscriptionResult:
        assert filename == "recording.webm"
        assert content == b"fake-audio"
        assert content_type == "audio/webm"
        return TranscriptionResult(text="오늘 조금 힘들었어.", language=language)


class FakeTTS:
    async def stream_speech(self, request: SpeechRequest) -> AudioStream:
        assert request.speaker_id == "character_a"

        async def chunks() -> AsyncIterator[bytes]:
            yield b"audio-"
            yield b"bytes"

        return AudioStream(chunks=chunks(), media_type="audio/mpeg")


class NotConfiguredSceneDirector:
    async def create_speaker_turn(
        self, request: SpeakerTurnRequest
    ) -> SpeakerTurnResult:
        del request
        raise ProviderConfigurationError("groq", "GROQ_API_KEY is not configured")


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    app.dependency_overrides = {}
    yield
    app.dependency_overrides = {}


def test_create_speaker_turn() -> None:
    app.dependency_overrides[get_scene_director_provider] = FakeSceneDirector

    response = client.post(
        "/api/v1/speaker-turns",
        json={
            "role": "PRIMARY",
            "user_text": "오늘 회사에서 힘든 일이 있었어.",
            "speaker": {
                "id": "character_a",
                "name": "루미",
                "concept": "사용자의 말을 차분하게 듣는 캐릭터입니다.",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["speaker_id"] == "character_a"
    assert response.json()["to"] == "USER"


def test_speaker_turn_rejects_more_than_one_other_participant() -> None:
    response = client.post(
        "/api/v1/speaker-turns",
        json={
            "role": "PRIMARY",
            "user_text": "안녕",
            "speaker": {
                "id": "character_a",
                "name": "루미",
                "concept": "사용자의 말을 차분하게 듣는 캐릭터입니다.",
            },
            "other_participants": [
                {"id": "character_b", "name": "하루", "concept": "다른 관점을 말하는 캐릭터입니다."},
                {"id": "character_c", "name": "새벽", "concept": "세 번째 캐릭터입니다."},
            ],
        },
    )

    assert response.status_code == 422


def test_missing_provider_configuration_returns_503() -> None:
    app.dependency_overrides[get_scene_director_provider] = (
        NotConfiguredSceneDirector
    )

    response = client.post(
        "/api/v1/speaker-turns",
        json={
            "role": "PRIMARY",
            "user_text": "안녕",
            "speaker": {
                "id": "character_a",
                "name": "루미",
                "concept": "사용자의 말을 차분하게 듣는 캐릭터입니다.",
            },
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"


def test_provider_rate_limit_remains_429() -> None:
    class RateLimitedSceneDirector:
        async def create_speaker_turn(
            self, request: SpeakerTurnRequest
        ) -> SpeakerTurnResult:
            del request
            raise ProviderRequestError(
                "groq",
                "Scene Director upstream returned HTTP 429: quota exhausted",
                status_code=429,
                error_code="rate_limit_exceeded",
                retry_after="60",
            )

    app.dependency_overrides[get_scene_director_provider] = (
        RateLimitedSceneDirector
    )
    response = client.post(
        "/api/v1/speaker-turns",
        json={
            "role": "PRIMARY",
            "user_text": "rate limit test",
            "speaker": {
                "id": "character_a",
                "name": "test character",
                "concept": "test character concept",
            },
        },
    )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert response.json()["error"]["code"] == "rate_limit_exceeded"
    assert response.json()["error"]["upstream_status"] == 429


def test_create_transcription() -> None:
    app.dependency_overrides[get_stt_provider] = FakeSTT

    response = client.post(
        "/api/v1/stt/transcriptions",
        files={"file": ("recording.webm", b"fake-audio", "audio/webm")},
        data={"language": "ko"},
    )

    assert response.status_code == 200
    assert response.json() == {"text": "오늘 조금 힘들었어.", "language": "ko"}


def test_transcription_rejects_non_audio_file() -> None:
    response = client.post(
        "/api/v1/stt/transcriptions",
        files={"file": ("notes.txt", b"not-audio", "text/plain")},
    )

    assert response.status_code == 415


def test_transcription_accepts_browser_webm_codec_content_type() -> None:
    app.dependency_overrides[get_stt_provider] = FakeSTT

    response = client.post(
        "/api/v1/stt/transcriptions",
        files={
            "file": (
                "recording.webm",
                b"fake-audio",
                "audio/webm;codecs=opus",
            )
        },
        data={"language": "ko"},
    )

    assert response.status_code == 200
    assert response.json()["text"] == "오늘 조금 힘들었어."


def test_stream_speech() -> None:
    app.dependency_overrides[get_tts_provider] = FakeTTS

    response = client.post(
        "/api/v1/tts/stream",
        json={
            "speaker_id": "character_a",
            "text": "천천히 말해도 괜찮아.",
            "emotion": "concern",
            "audio_format": "mp3",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.content == b"audio-bytes"
