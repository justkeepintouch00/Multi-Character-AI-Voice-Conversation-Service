from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import ValidationError

from app.domain.characters import DEVELOPMENT_CHARACTERS
from app.providers.base import (
    ProviderConfigurationError,
    ProviderInputError,
    ProviderRequestError,
    ProviderResponseError,
    ProviderTimeoutError,
    TranscriptionResult,
    TranscriptionSegment,
)
from app.providers.scene_director import (
    SCENE_DIRECTOR_INSTRUCTIONS,
    scene_plan_schema,
)
from app.schemas.scene_plan import ScenePlan, ScenePlanRequest


# Groq currently guarantees strict JSON Schema output for these production models.
# Other models use JSON Object Mode and are validated by Pydantic below.
STRICT_STRUCTURED_OUTPUT_MODELS = {
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
}

KOREAN_TRANSCRIPTION_PROMPT = (
    "한국어 일상 감정 대화입니다. 관계, 고민, 평가받는 느낌, 공감받고 싶다, "
    "조언은 필요 없다는 표현이 나올 수 있습니다. 자연스러운 한국어 문장부호를 사용합니다."
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

    async def create_scene_plan(self, request: ScenePlanRequest) -> ScenePlan:
        unknown_ids = set(request.character_ids) - set(DEVELOPMENT_CHARACTERS)
        if unknown_ids:
            raise ProviderInputError("groq", "Unknown character_id")
        if not self.api_key:
            raise ProviderConfigurationError("groq", "GROQ_API_KEY is not configured")

        schema = scene_plan_schema(request.character_ids)
        input_payload = {
            "user_text": request.user_text,
            "characters": [
                {
                    "id": character_id,
                    "name": DEVELOPMENT_CHARACTERS[character_id].name,
                    "persona": DEVELOPMENT_CHARACTERS[character_id].persona,
                }
                for character_id in request.character_ids
            ],
            "recent_messages": [
                message.model_dump(mode="json") for message in request.recent_messages
            ],
            "required_output_schema": schema,
        }
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SCENE_DIRECTOR_INSTRUCTIONS},
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
                    "name": "scene_plan",
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
                "max_completion_tokens": 1200,
                "stream": False,
            }
            response_payload = await self._request(payload)
            try:
                output_text = _extract_chat_content(response_payload)
                plan = ScenePlan.model_validate_json(output_text)
                plan.validate_speakers(set(request.character_ids))
                return plan
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
            "groq", "Scene Director returned an invalid scene plan"
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
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
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
                        "model": self.model,
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
        )


def _optional_float(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None
