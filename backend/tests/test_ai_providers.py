from __future__ import annotations

import asyncio
import json

import httpx

from app.providers.groq import (
    KOREAN_TRANSCRIPTION_PROMPT,
    GroqSceneDirector,
    GroqTranscriptionProvider,
)
from app.providers.scene_director import (
    COMMON_SPEAKER_POLICY,
    PRIMARY_SPEAKER_INSTRUCTIONS,
    SECONDARY_SPEAKER_INSTRUCTIONS,
)
from app.providers.typecast import TypecastTTSProvider
from app.schemas.scene_plan import SceneCharacter
from app.schemas.speaker_turn import SpeakerTurnRequest
from app.schemas.speech import SpeechRequest


CHARACTER_A = SceneCharacter(
    id="character_a",
    name="루미",
    concept="사용자의 말을 차분하게 듣고 맥락을 기억하는 대화 캐릭터입니다.",
    persona="차분하게 반응한다.",
    traits=["차분한"],
)
CHARACTER_B = SceneCharacter(
    id="character_b",
    name="하루",
    concept="앞 캐릭터의 말을 듣고 다른 관점을 자연스럽게 이어가는 캐릭터입니다.",
    persona="솔직하고 자연스럽게 말한다.",
    traits=["솔직한"],
)


def _primary_turn_payload(**overrides: object) -> dict:
    payload = {
        "speaker_id": "character_a",
        "to": "USER",
        "emotion": "calm",
        "text": "천천히 이야기해도 괜찮아.",
        "needs_second_speaker": False,
        "second_speaker_reason": "NONE",
    }
    payload.update(overrides)
    return payload


def test_groq_scene_director_uses_json_object_mode_for_llama() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/openai/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["model"] == "llama-3.3-70b-versatile"
        assert payload["response_format"] == {"type": "json_object"}
        body = json.loads(payload["messages"][1]["content"])
        assert body["speaker"]["id"] == "character_a"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(_primary_turn_payload())}}
                ],
            },
        )

    provider = GroqSceneDirector(
        api_key="test-key",
        base_url="https://api.groq.test/openai/v1",
        model="llama-3.3-70b-versatile",
        transport=httpx.MockTransport(handler),
    )
    turn = asyncio.run(
        provider.create_speaker_turn(
            SpeakerTurnRequest(
                role="PRIMARY",
                user_text="오늘 조금 힘들었어.",
                speaker=CHARACTER_A,
            )
        )
    )

    assert turn.speaker_id == "character_a"
    assert turn.needs_second_speaker is False


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
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(_primary_turn_payload())}}
                ]
            },
        )

    provider = GroqSceneDirector(
        api_key="test-key",
        base_url="https://api.groq.test/openai/v1",
        model="llama-3.3-70b-versatile",
        max_attempts=2,
        transport=httpx.MockTransport(handler),
    )
    turn = asyncio.run(
        provider.create_speaker_turn(
            SpeakerTurnRequest(
                role="PRIMARY",
                user_text="오늘 조금 힘들었어.",
                speaker=CHARACTER_A,
            )
        )
    )

    assert turn.speaker_id == "character_a"
    assert request_count == 2


def test_groq_scene_director_uses_flat_strict_schema_for_gpt_oss() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        response_format = payload["response_format"]
        assert response_format["type"] == "json_schema"
        schema = response_format["json_schema"]
        assert schema["strict"] is True
        assert schema["schema"]["additionalProperties"] is False
        assert set(schema["schema"]["required"]) == {
            "speaker_id", "to", "emotion", "text",
            "needs_second_speaker", "second_speaker_reason",
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                _primary_turn_payload(
                                    text="무슨 일이 있었는지 말해줄래?",
                                    emotion="neutral",
                                )
                            )
                        }
                    }
                ]
            },
        )

    provider = GroqSceneDirector(
        api_key="test-key",
        base_url="https://api.groq.test/openai/v1",
        model="openai/gpt-oss-20b",
        transport=httpx.MockTransport(handler),
    )
    turn = asyncio.run(
        provider.create_speaker_turn(
            SpeakerTurnRequest(
                role="PRIMARY",
                user_text="이야기를 들어줘.",
                speaker=CHARACTER_A,
            )
        )
    )

    assert turn.text == "무슨 일이 있었는지 말해줄래?"


def test_groq_scene_director_second_speaker_ignores_own_decision_fields() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        schema = payload["messages"][1]["content"]
        body = json.loads(schema)
        assert "needs_second_speaker" not in body["output_contract"]["required_keys"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "speaker_id": "character_b",
                                    "to": "USER",
                                    "emotion": "calm",
                                    "text": "나는 조금 다르게 봐.",
                                }
                            )
                        }
                    }
                ]
            },
        )

    provider = GroqSceneDirector(
        api_key="test-key",
        base_url="https://api.groq.test/openai/v1",
        model="llama-3.3-70b-versatile",
        transport=httpx.MockTransport(handler),
    )
    turn = asyncio.run(
        provider.create_speaker_turn(
            SpeakerTurnRequest(
                role="SECONDARY",
                user_text="오늘 조금 힘들었어.",
                speaker=CHARACTER_B,
                other_participants=[CHARACTER_A],
            )
        )
    )

    assert turn.speaker_id == "character_b"
    assert turn.needs_second_speaker is False


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


def test_primary_speaker_defaults_to_answering_alone() -> None:
    assert "기본적으로 당신 혼자 답한다" in PRIMARY_SPEAKER_INSTRUCTIONS
    assert "단순 동의" in PRIMARY_SPEAKER_INSTRUCTIONS
    assert "DIFFERING_VIEWPOINT" in PRIMARY_SPEAKER_INSTRUCTIONS
    assert "AGREEMENT_BACKUP" in PRIMARY_SPEAKER_INSTRUCTIONS
    assert "아주 드물게" in PRIMARY_SPEAKER_INSTRUCTIONS
    assert "비공개 기억은 전달되지 않는다" in PRIMARY_SPEAKER_INSTRUCTIONS
    assert "대화 복구 상황" in PRIMARY_SPEAKER_INSTRUCTIONS
    assert "needs_second_speaker를 항상 false로 둔다" in PRIMARY_SPEAKER_INSTRUCTIONS


def test_secondary_speaker_continues_in_the_same_scene() -> None:
    assert "다른 관점 1문장만" in SECONDARY_SPEAKER_INSTRUCTIONS
    assert "독립된 설명문을 하나 더 붙이는 방식이 아니라" in SECONDARY_SPEAKER_INSTRUCTIONS
    assert "기억했으면 좋겠어요" in SECONDARY_SPEAKER_INSTRUCTIONS
    assert "넘겨짚지 않는다" in SECONDARY_SPEAKER_INSTRUCTIONS


def test_common_policy_covers_shared_conversation_quality_rules() -> None:
    assert "질문의 핵심에 먼저 답한다" in COMMON_SPEAKER_POLICY
    assert "2~4개의 짧은 문장" in COMMON_SPEAKER_POLICY
    assert "같은 내용을 다시 요구하는 질문을 하지 않는다" in COMMON_SPEAKER_POLICY
    assert "정서적으로 정상화" in COMMON_SPEAKER_POLICY
    assert "상투적 마무리를 사용하지 않는다" in COMMON_SPEAKER_POLICY
    assert "질문을 반드시 만들지 않는다" in COMMON_SPEAKER_POLICY
    assert "질문 하나만 한다" in COMMON_SPEAKER_POLICY
    assert "변명 없이 사과" in COMMON_SPEAKER_POLICY
    assert "추가 설명 요구" in COMMON_SPEAKER_POLICY
    assert "조언, 해결책, 원인 분석을 하지 않는다" in COMMON_SPEAKER_POLICY
    assert "청취 시간이 사용자의 발화를 압도하지 않도록" in COMMON_SPEAKER_POLICY
    assert "memory_context에 없는 사실은 지어내지 않는다" in COMMON_SPEAKER_POLICY
    assert PRIMARY_SPEAKER_INSTRUCTIONS.count(COMMON_SPEAKER_POLICY) == 1
    assert SECONDARY_SPEAKER_INSTRUCTIONS.count(COMMON_SPEAKER_POLICY) == 1


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

