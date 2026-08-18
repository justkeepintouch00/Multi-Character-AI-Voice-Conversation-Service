from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import ValidationError

from app.providers.base import (
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
    ProviderTimeoutError,
    TranscriptionResult,
    TranscriptionSegment,
)
from app.providers.scene_director import (
    PRIMARY_SPEAKER_INSTRUCTIONS,
    SECONDARY_SPEAKER_INSTRUCTIONS,
    primary_speaker_turn_schema,
    secondary_speaker_turn_schema,
)
from app.schemas.speaker_turn import SpeakerTurnRequest, SpeakerTurnResult


# Groq currently guarantees strict JSON Schema output for these production models.
# Other models use JSON Object Mode and are validated by Pydantic below.
STRICT_STRUCTURED_OUTPUT_MODELS = {
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
}

KOREAN_TRANSCRIPTION_PROMPT = (
    "GPT, 프로젝트, 면접, 회사, 인공지능에 관한 개인적인 고민을 말하는 "
    "한국어 1인칭 일상 대화입니다. 발화를 한국어 그대로 받아쓰고, "
    "영어로 번역하거나 내용을 요약·각색하지 마세요."
)


def _extract_chat_content(payload: dict[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderResponseError(
            "groq", "Scene Director returned no text output"
        ) from exc
    if not isinstance(content, str) or not content.strip():
        raise ProviderResponseError("groq", "Scene Director returned empty output")
    return content


class GroqSceneDirector:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model: str,
        max_attempts: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_attempts = min(max(max_attempts, 1), 3)
        self.transport = transport

    async def create_speaker_turn(
        self, request: SpeakerTurnRequest
    ) -> SpeakerTurnResult:
        if not self.api_key:
            raise ProviderConfigurationError("groq", "GROQ_API_KEY is not configured")

        other_participant_ids = [
            character.id for character in request.other_participants
        ]
        memory_context_ids = [item.id for item in request.memory_context]
        if request.role == "PRIMARY":
            instructions = PRIMARY_SPEAKER_INSTRUCTIONS
            schema = primary_speaker_turn_schema(
                request.speaker.id, other_participant_ids, memory_context_ids
            )
            schema_name = "primary_speaker_turn"
        else:
            instructions = SECONDARY_SPEAKER_INSTRUCTIONS
            schema = secondary_speaker_turn_schema(
                request.speaker.id, other_participant_ids, memory_context_ids
            )
            schema_name = "secondary_speaker_turn"

        input_payload = {
            "user_text": request.user_text,
            "user_display_name": request.user_display_name,
            "speaker": request.speaker.model_dump(mode="json"),
            "other_participants": [
                character.model_dump(mode="json")
                for character in request.other_participants
            ],
            "recent_messages": [
                message.model_dump(mode="json") for message in request.recent_messages
            ],
            "memory_context": [
                item.model_dump(mode="json") for item in request.memory_context
            ],
            "required_output_schema": schema,
        }
        messages: list[dict[str, str]] = [
            {"role": "system", "content": instructions},
            {
                "role": "user",
                "content": json.dumps(input_payload, ensure_ascii=False),
            },
        ]
        response_format: dict[str, Any]
        if self.model in STRICT_STRUCTURED_OUTPUT_MODELS:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            }
        else:
            response_format = {"type": "json_object"}

        last_validation_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            payload = {
                "model": self.model,
                "messages": messages,
                "response_format": response_format,
                "temperature": 0.2,
                "max_completion_tokens": 600,
                "stream": False,
            }
            response_payload = await self._request(payload)
            try:
                output_text = _extract_chat_content(response_payload)
                turn = SpeakerTurnResult.model_validate_json(output_text)
                turn.validate_speaker(request.speaker.id)
                return turn
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_validation_error = exc
                if attempt < self.max_attempts:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "직전 출력이 required_output_schema 검증에 실패했다. "
                                "스키마에 맞는 JSON 객체만 다시 출력하라."
                            ),
                        }
                    )

        raise ProviderResponseError(
            "groq", "Scene Director returned an invalid speaker turn"
        ) from last_validation_error

    async def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=httpx.Timeout(45.0),
            ) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("groq", "Scene Director timed out") from exc
        except httpx.RequestError as exc:
            raise ProviderRequestError("groq", "Scene Director request failed") from exc

        if response.is_error:
            raise ProviderRequestError(
                "groq",
                f"Scene Director upstream returned HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ProviderResponseError(
                "groq", "Scene Director returned invalid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderResponseError(
                "groq", "Scene Director returned an invalid response"
            )
        return payload


class GroqTranscriptionProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model: str,
        fallback_model: str | None = None,
        fallback_avg_logprob_threshold: float = -0.25,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.fallback_model = fallback_model
        self.fallback_avg_logprob_threshold = fallback_avg_logprob_threshold
        self.transport = transport

    async def transcribe(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str,
        language: str,
    ) -> TranscriptionResult:
        if not self.api_key:
            raise ProviderConfigurationError("groq", "GROQ_API_KEY is not configured")

        primary_result = await self._transcribe_once(
            filename=filename,
            content=content,
            content_type=content_type,
            language=language,
            model=self.model,
        )
        primary_avg_logprob = _average_segment_logprob(primary_result.segments)
        low_confidence = (
            primary_avg_logprob is not None
            and primary_avg_logprob < self.fallback_avg_logprob_threshold
        )
        should_retry = (
            self.fallback_model is not None
            and self.fallback_model != self.model
            and low_confidence
        )
        if not should_retry:
            return primary_result

        fallback_result = await self._transcribe_once(
            filename=filename,
            content=content,
            content_type=content_type,
            language=language,
            model=self.fallback_model,
        )
        return TranscriptionResult(
            text=fallback_result.text,
            language=fallback_result.language,
            duration_seconds=fallback_result.duration_seconds,
            segments=fallback_result.segments,
            model=fallback_result.model,
            fallback_used=True,
            fallback_reason="low_avg_logprob",
            primary_model=self.model,
            primary_text=primary_result.text,
            primary_avg_logprob=primary_avg_logprob,
        )

    async def _transcribe_once(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str,
        language: str,
        model: str,
    ) -> TranscriptionResult:
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=httpx.Timeout(90.0),
            ) as client:
                response = await client.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"file": (filename, content, content_type)},
                    data={
                        "model": model,
                        "language": language,
                        "prompt": (
                            KOREAN_TRANSCRIPTION_PROMPT
                            if language.lower() == "ko"
                            else "Natural conversational speech."
                        ),
                        "response_format": "verbose_json",
                        "temperature": "0",
                    },
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("groq", "Transcription timed out") from exc
        except httpx.RequestError as exc:
            raise ProviderRequestError("groq", "Transcription request failed") from exc

        if response.is_error:
            raise ProviderRequestError(
                "groq",
                f"Transcription upstream returned HTTP {response.status_code}",
            )
        try:
            payload = response.json()
            text = payload["text"].strip()
        except (json.JSONDecodeError, KeyError, AttributeError) as exc:
            raise ProviderResponseError(
                "groq", "Transcription returned an invalid response"
            ) from exc
        if not text:
            raise ProviderResponseError("groq", "Transcription returned empty text")

        duration_seconds = _optional_float(payload.get("duration"))
        segments: list[TranscriptionSegment] = []
        raw_segments = payload.get("segments", [])
        if isinstance(raw_segments, list):
            for raw_segment in raw_segments:
                if not isinstance(raw_segment, dict):
                    continue
                segment_text = raw_segment.get("text", "")
                segments.append(
                    TranscriptionSegment(
                        id=(
                            raw_segment["id"]
                            if isinstance(raw_segment.get("id"), int)
                            else None
                        ),
                        start_seconds=_optional_float(raw_segment.get("start")),
                        end_seconds=_optional_float(raw_segment.get("end")),
                        text=(
                            segment_text.strip()
                            if isinstance(segment_text, str)
                            else ""
                        ),
                        avg_logprob=_optional_float(raw_segment.get("avg_logprob")),
                        compression_ratio=_optional_float(
                            raw_segment.get("compression_ratio")
                        ),
                        no_speech_prob=_optional_float(
                            raw_segment.get("no_speech_prob")
                        ),
                    )
                )
        return TranscriptionResult(
            text=text,
            language=language,
            duration_seconds=duration_seconds,
            segments=tuple(segments),
            model=model,
        )


def _optional_float(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _average_segment_logprob(
    segments: tuple[TranscriptionSegment, ...],
) -> float | None:
    values = [
        segment.avg_logprob
        for segment in segments
        if segment.avg_logprob is not None
    ]
    if not values:
        return None
    return sum(values) / len(values)
