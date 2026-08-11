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
    TranscriptionResult,
)
from app.schemas.scene_plan import ScenePlan, ScenePlanRequest
from app.schemas.speech import SpeechRequest


client = TestClient(app)


class FakeSceneDirector:
    async def create_scene_plan(self, request: ScenePlanRequest) -> ScenePlan:
        return ScenePlan.model_validate(
            {
                "scene_action": "CHARACTER_SEQUENCE",
                "turns": [
                    {
                        "speaker_id": request.character_ids[0],
                        "to": "USER",
                        "emotion": "concern",
                        "text": "많이 지쳤겠네. 천천히 말해도 괜찮아.",
                    }
                ],
                "return_turn_to": "USER",
                "max_internal_turns": 1,
            }
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
    async def create_scene_plan(self, request: ScenePlanRequest) -> ScenePlan:
        del request
        raise ProviderConfigurationError("groq", "GROQ_API_KEY is not configured")


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    app.dependency_overrides = {}
    yield
    app.dependency_overrides = {}


def test_create_scene_plan() -> None:
    app.dependency_overrides[get_scene_director_provider] = FakeSceneDirector

    response = client.post(
        "/api/v1/scene-plans",
        json={
            "user_text": "오늘 회사에서 힘든 일이 있었어.",
            "character_ids": ["character_a", "character_b"],
        },
    )

    assert response.status_code == 200
    assert response.json()["turns"][0]["speaker_id"] == "character_a"
    assert response.json()["return_turn_to"] == "USER"


def test_scene_plan_rejects_more_than_two_characters() -> None:
    response = client.post(
        "/api/v1/scene-plans",
        json={
            "user_text": "안녕",
            "character_ids": ["character_a", "character_b", "character_c"],
        },
    )

    assert response.status_code == 422


def test_missing_provider_configuration_returns_503() -> None:
    app.dependency_overrides[get_scene_director_provider] = (
        NotConfiguredSceneDirector
    )

    response = client.post(
        "/api/v1/scene-plans",
        json={"user_text": "안녕", "character_ids": ["character_a"]},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"


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
