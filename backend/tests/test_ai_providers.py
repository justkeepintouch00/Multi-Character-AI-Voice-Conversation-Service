from __future__ import annotations

import asyncio
import json

import httpx

from app.providers.groq import (
    KOREAN_TRANSCRIPTION_PROMPT,
    GroqSceneDirector,
    GroqTranscriptionProvider,
)
from app.providers.scene_director import SCENE_DIRECTOR_INSTRUCTIONS
from app.providers.typecast import TypecastTTSProvider
from app.schemas.scene_plan import ScenePlanRequest
from app.schemas.speech import SpeechRequest


def test_groq_scene_director_uses_json_object_mode_for_llama() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/openai/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["model"] == "llama-3.3-70b-versatile"
        assert payload["response_format"] == {"type": "json_object"}
        plan = {
            "scene_action": "CHARACTER_SEQUENCE",
            "turns": [
                {
                    "speaker_id": "character_a",
                    "to": "USER",
                    "emotion": "calm",
                    "text": "천천히 이야기해도 괜찮아.",
                }
            ],
            "return_turn_to": "USER",
            "max_internal_turns": 1,
        }
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(plan)}}],
            },
        )

    provider = GroqSceneDirector(
        api_key="test-key",
        base_url="https://api.groq.test/openai/v1",
        model="llama-3.3-70b-versatile",
        transport=httpx.MockTransport(handler),
    )
    plan = asyncio.run(
        provider.create_scene_plan(
            ScenePlanRequest(
                user_text="오늘 조금 힘들었어.",
                character_ids=["character_a"],
            )
        )
    )

    assert plan.return_turn_to == "USER"
    assert len(plan.turns) == 1


def test_groq_scene_director_retries_invalid_llama_output() -> None:
    request_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "{}"}}]},
            )
        plan = {
            "scene_action": "CHARACTER_SEQUENCE",
            "turns": [
                {
                    "speaker_id": "character_a",
                    "to": "USER",
                    "emotion": "calm",
                    "text": "천천히 이야기해도 괜찮아.",
                }
            ],
            "return_turn_to": "USER",
            "max_internal_turns": 1,
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(plan)}}]},
        )

    provider = GroqSceneDirector(
        api_key="test-key",
        base_url="https://api.groq.test/openai/v1",
        model="llama-3.3-70b-versatile",
        max_attempts=2,
        transport=httpx.MockTransport(handler),
    )
    plan = asyncio.run(
        provider.create_scene_plan(
            ScenePlanRequest(
                user_text="오늘 조금 힘들었어.",
                character_ids=["character_a"],
            )
        )
    )

    assert plan.turns[0].speaker_id == "character_a"
    assert request_count == 2


def test_groq_scene_director_uses_strict_schema_for_supported_model() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["strict"] is True
        plan = {
            "scene_action": "CHARACTER_SEQUENCE",
            "turns": [
                {
                    "speaker_id": "character_a",
                    "to": "USER",
                    "emotion": "neutral",
                    "text": "무슨 일이 있었는지 말해줄래?",
                }
            ],
            "return_turn_to": "USER",
            "max_internal_turns": 1,
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(plan)}}]},
        )

    provider = GroqSceneDirector(
        api_key="test-key",
        base_url="https://api.groq.test/openai/v1",
        model="openai/gpt-oss-20b",
        transport=httpx.MockTransport(handler),
    )
    plan = asyncio.run(
        provider.create_scene_plan(
            ScenePlanRequest(
                user_text="이야기를 들어줘.",
                character_ids=["character_a"],
            )
        )
    )

    assert plan.max_internal_turns == 1


def test_groq_transcription_sends_multipart_audio() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/openai/v1/audio/transcriptions"
        assert request.headers["content-type"].startswith("multipart/form-data")
        assert b'verbose_json' in request.content
        assert b'name="prompt"' in request.content
        assert KOREAN_TRANSCRIPTION_PROMPT.encode() in request.content
        return httpx.Response(
            200,
            json={
                "text": "테스트 음성입니다.",
                "duration": 1.8,
                "segments": [
                    {
                        "id": 0,
                        "start": 0.0,
                        "end": 1.8,
                        "text": "테스트 음성입니다.",
                        "avg_logprob": -0.12,
                        "compression_ratio": 1.2,
                        "no_speech_prob": 0.02,
                    }
                ],
            },
        )

    provider = GroqTranscriptionProvider(
        api_key="test-key",
        base_url="https://api.groq.test/openai/v1",
        model="whisper-large-v3-turbo",
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(
        provider.transcribe(
            filename="recording.webm",
            content=b"fake-audio",
            content_type="audio/webm",
            language="ko",
        )
    )

    assert result.text == "테스트 음성입니다."
    assert result.language == "ko"
    assert result.duration_seconds == 1.8
    assert result.segments[0].avg_logprob == -0.12
    assert result.segments[0].no_speech_prob == 0.02
    assert result.model == "whisper-large-v3-turbo"
    assert result.fallback_used is False
    assert result.language_mismatch is False


def test_groq_transcription_retries_large_v3_for_low_confidence_turbo() -> None:
    requested_models: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        is_fallback = b"whisper-large-v3\r\n" in request.content
        requested_models.append(
            "whisper-large-v3" if is_fallback else "whisper-large-v3-turbo"
        )
        if not is_fallback:
            return httpx.Response(
                200,
                json={
                    "text": "왜곡된 1차 문장",
                    "duration": 20.0,
                    "segments": [
                        {
                            "id": 0,
                            "start": 0.0,
                            "end": 20.0,
                            "text": "왜곡된 1차 문장",
                            "avg_logprob": -0.292,
                            "compression_ratio": 1.2,
                            "no_speech_prob": 0.0,
                        }
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "text": "정확도가 개선된 최종 문장",
                "duration": 20.0,
                "segments": [
                    {
                        "id": 0,
                        "start": 0.0,
                        "end": 20.0,
                        "text": "정확도가 개선된 최종 문장",
                        "avg_logprob": -0.1,
                        "compression_ratio": 1.1,
                        "no_speech_prob": 0.0,
                    }
                ],
            },
        )

    provider = GroqTranscriptionProvider(
        api_key="test-key",
        base_url="https://api.groq.test/openai/v1",
        model="whisper-large-v3-turbo",
        fallback_model="whisper-large-v3",
        fallback_avg_logprob_threshold=-0.25,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(
        provider.transcribe(
            filename="recording.webm",
            content=b"fake-audio",
            content_type="audio/webm",
            language="ko",
        )
    )

    assert requested_models == ["whisper-large-v3-turbo", "whisper-large-v3"]
    assert result.text == "정확도가 개선된 최종 문장"
    assert result.model == "whisper-large-v3"
    assert result.fallback_used is True
    assert result.primary_text == "왜곡된 1차 문장"
    assert result.primary_avg_logprob == -0.292
    assert result.fallback_reason == "low_avg_logprob"


def test_groq_transcription_retries_when_korean_result_is_english() -> None:
    request_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return httpx.Response(
                200,
                json={
                    "text": "I think I have a problem with GPT and my project.",
                    "duration": 17.8,
                    "segments": [
                        {
                            "id": 0,
                            "start": 0.0,
                            "end": 17.8,
                            "text": "I think I have a problem with GPT and my project.",
                            "avg_logprob": -0.13,
                            "compression_ratio": 1.2,
                            "no_speech_prob": 0.0,
                        }
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "text": "GPT로 프로젝트를 하는 것이 고민이야.",
                "duration": 17.8,
                "segments": [
                    {
                        "id": 0,
                        "start": 0.0,
                        "end": 17.8,
                        "text": "GPT로 프로젝트를 하는 것이 고민이야.",
                        "avg_logprob": -0.11,
                        "compression_ratio": 1.1,
                        "no_speech_prob": 0.0,
                    }
                ],
            },
        )

    provider = GroqTranscriptionProvider(
        api_key="test-key",
        base_url="https://api.groq.test/openai/v1",
        model="whisper-large-v3-turbo",
        fallback_model="whisper-large-v3",
        fallback_avg_logprob_threshold=-0.25,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(
        provider.transcribe(
            filename="recording.webm",
            content=b"fake-audio",
            content_type="audio/webm",
            language="ko",
        )
    )

    assert request_count == 2
    assert result.text == "GPT로 프로젝트를 하는 것이 고민이야."
    assert result.fallback_used is True
    assert result.fallback_reason == "language_mismatch"
    assert result.language_mismatch is False


def test_scene_director_defaults_to_one_speaker_without_distinct_view() -> None:
    assert "가장 적합한 캐릭터 한 명만 답한다" in SCENE_DIRECTOR_INSTRUCTIONS
    assert "단순 동의" in SCENE_DIRECTOR_INSTRUCTIONS
    assert "질문의 핵심에 먼저 답한다" in SCENE_DIRECTOR_INSTRUCTIONS
    assert "모든 발화를 고민 상담으로 취급" in SCENE_DIRECTOR_INSTRUCTIONS
    assert "대화 복구 상황" in SCENE_DIRECTOR_INSTRUCTIONS
    assert "변명 없이 사과" in SCENE_DIRECTOR_INSTRUCTIONS
    assert "추가 설명 요구" in SCENE_DIRECTOR_INSTRUCTIONS
    assert "조언, 해결책, 원인 분석을 하지 않는다" in SCENE_DIRECTOR_INSTRUCTIONS
    assert "3~5문장으로 충분히 반영" in SCENE_DIRECTOR_INSTRUCTIONS
    assert "같은 내용을 다시 요구하는 질문을 하지 않는다" in SCENE_DIRECTOR_INSTRUCTIONS
    assert "정서적으로 정상화" in SCENE_DIRECTOR_INSTRUCTIONS
    assert "상투적 마무리를 사용하지 않는다" in SCENE_DIRECTOR_INSTRUCTIONS
    assert "질문을 반드시 만들지 않는다" in SCENE_DIRECTOR_INSTRUCTIONS
    assert "질문 하나만 한다" in SCENE_DIRECTOR_INSTRUCTIONS
    assert "persona와 traits" in SCENE_DIRECTOR_INSTRUCTIONS


def test_typecast_tts_stream_maps_domain_emotion() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/text-to-speech/stream"
        payload = json.loads(request.content)
        assert payload["voice_id"] == "tc_test_voice"
        assert payload["prompt"]["emotion_preset"] == "tonedown"
        assert payload["output"]["audio_format"] == "mp3"
        return httpx.Response(200, content=b"streamed-audio")

    async def run_test() -> bytes:
        provider = TypecastTTSProvider(
            api_key="test-key",
            base_url="https://api.typecast.test",
            model="ssfm-v30",
            voice_map={"character_a": "tc_test_voice"},
            transport=httpx.MockTransport(handler),
        )
        audio = await provider.stream_speech(
            SpeechRequest(
                speaker_id="character_a",
                text="천천히 말해도 괜찮아.",
                emotion="concern",
                audio_format="mp3",
            )
        )
        return b"".join([chunk async for chunk in audio.chunks])

    assert asyncio.run(run_test()) == b"streamed-audio"
