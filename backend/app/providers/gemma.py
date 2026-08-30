from __future__ import annotations

import json
import re
from typing import Any

import httpx
from pydantic import ValidationError

from app.observability import METRICS, log_event, record_llm_usage
from app.observability.langsmith import finish_trace, trace_llm_call

from app.providers.base import (
    ProviderRequestError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from app.providers.scene_director import (
    PRIMARY_SPEAKER_INSTRUCTIONS,
    SECONDARY_SPEAKER_INSTRUCTIONS,
    primary_speaker_turn_schema,
    secondary_speaker_turn_schema,
)
from app.schemas.speaker_turn import SpeakerTurnRequest, SpeakerTurnResult


PROVIDER_NAME = "gemma4_e2b"


def _extract_error_metadata(
    response: httpx.Response,
) -> tuple[str | None, str | None]:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None, None
    code = str(error["code"]) if error.get("code") is not None else None
    message = (
        str(error["message"]) if error.get("message") is not None else None
    )
    return code, message


def _extract_chat_content(payload: dict[str, Any]) -> str:
    """Extract a usable assistant string from OpenAI/llama.cpp responses."""
    choices = payload.get("choices")
    candidates: list[Any] = []
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            message = choice.get("message")
            if isinstance(message, dict):
                candidates.extend([message.get("content"), message.get("text"), message.get("reasoning_content")])
            candidates.append(choice.get("text"))
    candidates.extend([payload.get("text"), payload.get("content")])
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    raise ProviderResponseError(PROVIDER_NAME, "Gemma Scene Director returned empty output")


def _single_speaker_text(text: str, *, speaker_name: str, other_names: list[str]) -> str:
    """Keep only the requested speaker when a local model emits labeled turns."""
    cleaned = re.sub(r"\x60\x60\x60(?:json)?|\x60\x60\x60", "", text, flags=re.IGNORECASE).strip()
    names = [name.strip() for name in [speaker_name, *other_names] if name.strip()]
    if not names:
        return cleaned
    label_pattern = "|".join(re.escape(name) for name in names)
    matches = list(re.finditer(rf"(?<!\S)({label_pattern})\s*[:：]", cleaned))
    if not matches:
        return cleaned
    for index, match in enumerate(matches):
        if match.group(1) != speaker_name:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned)
        segment = cleaned[match.end() : end].strip(" \t\r\n-—")
        if segment:
            return segment
    raise ValueError("Gemma output contains no turn for the requested speaker")


def _extract_json_object(content: str) -> dict[str, Any]:
    """Accept plain JSON and tolerate a surrounding code fence or explanation."""

    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        object_start = content.find("{")
        if object_start < 0:
            raise
        payload, _ = json.JSONDecoder().raw_decode(content[object_start:])
    if not isinstance(payload, dict):
        raise ValueError("Gemma output is not a JSON object")
    return payload

_VALID_EMOTIONS = {
    "neutral", "calm", "concern", "happy", "sad", "angry",
    "whisper", "encouraging", "serious",
}
_VALID_SECOND_SPEAKER_REASONS = {
    "NONE", "DIFFERING_VIEWPOINT", "AGREEMENT_BACKUP",
}
_VALID_SENSITIVITIES = {"PUBLIC", "PERSONAL", "PRIVATE", "HIGH"}


def _normalize_turn_payload(
    payload: dict[str, Any],
    *,
    request: SpeakerTurnRequest,
    other_participant_ids: list[str],
) -> dict[str, Any]:
    """Make a local model's best-effort JSON safe for the strict turn schema."""
    raw_text = payload.get("text")
    if not isinstance(raw_text, str) or not raw_text.strip():
        for key in ("message", "response", "reply", "answer", "content", "greeting"):
            candidate = payload.get(key)
            if isinstance(candidate, str) and candidate.strip():
                raw_text = candidate
                break
    text = raw_text.strip() if isinstance(raw_text, str) else ""
    if not text:
        raise ValueError("Gemma output text is empty")
    raw_to = payload.get("to")
    to = raw_to if isinstance(raw_to, str) else "USER"
    if to not in {"USER", *other_participant_ids}:
        to = "USER"

    raw_emotion = payload.get("emotion")
    emotion = raw_emotion if isinstance(raw_emotion, str) else "neutral"
    if emotion not in _VALID_EMOTIONS:
        emotion = "neutral"

    raw_reason = payload.get("second_speaker_reason")
    reason = raw_reason if isinstance(raw_reason, str) else "NONE"
    if reason not in _VALID_SECOND_SPEAKER_REASONS:
        reason = "NONE"

    raw_extracted = payload.get("extracted_memory")
    extracted = raw_extracted if isinstance(raw_extracted, dict) else {}
    raw_relation = extracted.get("graph_relation")
    relation = raw_relation if isinstance(raw_relation, dict) else {}
    sensitivity = extracted.get("sensitivity")
    if sensitivity not in _VALID_SENSITIVITIES:
        sensitivity = "PERSONAL"
    memory_content = extracted.get("content")
    if not isinstance(memory_content, str):
        memory_content = ""
    has_memory = extracted.get("has_memory") is True and bool(memory_content.strip())

    raw_disclosed = payload.get("disclosed_memory_ids")
    disclosed = (
        [item for item in raw_disclosed if isinstance(item, str)]
        if isinstance(raw_disclosed, list)
        else []
    )
    allowed_memory_ids = {str(item.id) for item in request.memory_context}
    disclosed = [item for item in disclosed if item in allowed_memory_ids][:5]

    return {
        # Routing is a server fact, never a value delegated to the model.
        "speaker_id": request.speaker.id,
        "to": to,
        "emotion": emotion,
        "text": text[:1000],
        "needs_second_speaker": (
            payload.get("needs_second_speaker") is True
            if request.role == "PRIMARY"
            else False
        ),
        "second_speaker_reason": reason if request.role == "PRIMARY" else "NONE",
        "extracted_memory": {
            "has_memory": has_memory,
            "content": memory_content[:500] if has_memory else "",
            "sensitivity": sensitivity,
            "graph_relation": {
                "has_relation": relation.get("has_relation") is True and has_memory,
                "source_entity": str(relation.get("source_entity") or "")[:160],
                "relation": str(relation.get("relation") or "")[:80],
                "target_entity": str(relation.get("target_entity") or "")[:160],
                "summary": str(relation.get("summary") or "")[:300],
            },
        },
        "disclosed_memory_ids": disclosed,
    }

class GemmaSceneDirector:
    """Scene Director backed by a local Gemma 4 E2B OpenAI-compatible server."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str = "gemma4-e2b",
        api_key: str | None = None,
        max_attempts: int = 2,
        timeout_seconds: float = 180.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.max_attempts = min(max(max_attempts, 1), 3)
        self.timeout_seconds = max(timeout_seconds, 1.0)
        self.transport = transport

    async def create_speaker_turn(
        self, request: SpeakerTurnRequest
    ) -> SpeakerTurnResult:
        other_participant_ids = [
            character.id for character in request.other_participants
        ]
        memory_context_ids = [item.id for item in request.memory_context]
        if request.role == "PRIMARY":
            instructions = PRIMARY_SPEAKER_INSTRUCTIONS
            schema = primary_speaker_turn_schema(
                request.speaker.id,
                other_participant_ids,
                memory_context_ids,
            )
        else:
            instructions = SECONDARY_SPEAKER_INSTRUCTIONS
            schema = secondary_speaker_turn_schema(
                request.speaker.id,
                other_participant_ids,
                memory_context_ids,
            )

        input_payload = {
            "user_text": request.user_text,
            "user_display_name": request.user_display_name,
            "speaker": request.speaker.model_dump(mode="json"),
            "other_participants": [
                character.model_dump(mode="json")
                for character in request.other_participants
            ],
            "recent_messages": [
                message.model_dump(mode="json")
                for message in request.recent_messages
            ],
            "memory_context": [
                item.model_dump(mode="json")
                for item in request.memory_context
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

        last_validation_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            output_text = ""
            response_payload = await self._request(
                {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.2,
                    "top_p": 0.95,
                    "max_tokens": 768 if attempt == 1 else 1280,
                    "response_format": {"type": "json_object"},
                    "stream": True,
                    # Ask OpenAI-compatible local servers to include usage.
                    "stream_options": {"include_usage": True},
                }
            )
            try:
                output_text = _extract_chat_content(response_payload)
                output_payload = _extract_json_object(output_text)
                output_payload = _normalize_turn_payload(
                    output_payload,
                    request=request,
                    other_participant_ids=other_participant_ids,
                )
                output_payload["text"] = _single_speaker_text(
                    output_payload["text"],
                    speaker_name=request.speaker.name,
                    other_names=[item.name for item in request.other_participants],
                )[:1000]
                turn = SpeakerTurnResult.model_validate(output_payload)
                turn.validate_speaker(request.speaker.id)
                return turn
            except (ProviderResponseError, json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_validation_error = exc
                if attempt < self.max_attempts:
                    METRICS.increment(
                        "llm_retries_total",
                        provider=PROVIDER_NAME,
                        model=self.model,
                        reason="invalid_structured_output",
                    )
                    if output_text:
                        messages.append(
                            {
                                "role": "assistant",
                                "content": output_text,
                            }
                        )
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "직전 출력이 없거나 required_output_schema 검증에 실패했다. "
                                "설명과 마크다운 없이 스키마에 맞는 JSON 객체만 "
                                "다시 출력하라."
                            ),
                        }
                    )

        raise ProviderResponseError(
            PROVIDER_NAME,
            "Gemma Scene Director returned an invalid speaker turn",
        ) from last_validation_error

    async def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=httpx.Timeout(self.timeout_seconds),
            ) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                PROVIDER_NAME, "Gemma Scene Director timed out"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderRequestError(
                PROVIDER_NAME,
                "Gemma local server request failed",
            ) from exc

        if response.is_error:
            error_code, error_message = _extract_error_metadata(response)
            message = (
                "Gemma Scene Director upstream returned "
                f"HTTP {response.status_code}"
            )
            if error_message:
                message = f"{message}: {error_message}"
            raise ProviderRequestError(
                PROVIDER_NAME,
                message,
                status_code=response.status_code,
                error_code=error_code,
                retry_after=response.headers.get("retry-after"),
            )

        try:
            response_payload = self._decode_response(response)
        except json.JSONDecodeError as exc:
            raise ProviderResponseError(
                PROVIDER_NAME,
                "Gemma Scene Director returned invalid JSON",
            ) from exc
        if not isinstance(response_payload, dict):
            raise ProviderResponseError(
                PROVIDER_NAME,
                "Gemma Scene Director returned an invalid response",
            )
        record_llm_usage(
            PROVIDER_NAME,
            self.model,
            response_payload.get("usage"),
        )
        return response_payload

    @staticmethod
    def _decode_response(response: httpx.Response) -> dict[str, Any]:
        """Decode either an OpenAI JSON response or an OpenAI-compatible SSE."""
        content_type = response.headers.get("content-type", "").lower()
        if "text/event-stream" not in content_type:
            payload = response.json()
            if not isinstance(payload, dict):
                raise ProviderResponseError(
                    PROVIDER_NAME,
                    "Gemma Scene Director returned an invalid response",
                )
            return payload

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        usage: dict[str, Any] | None = None
        for line in response.text.splitlines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            chunk = json.loads(data)
            if not isinstance(chunk, dict):
                continue
            chunk_usage = chunk.get("usage")
            if isinstance(chunk_usage, dict):
                usage = chunk_usage
            choices = chunk.get("choices")
            if not isinstance(choices, list) or not choices:
                continue
            choice = choices[0]
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            message = choice.get("message")
            parts = [part for part in (delta, message) if isinstance(part, dict)]
            for part in parts:
                for key in ("content", "text"):
                    value = part.get(key)
                    if isinstance(value, str):
                        content_parts.append(value)
                for key in ("reasoning_content", "reasoning"):
                    value = part.get(key)
                    if isinstance(value, str):
                        reasoning_parts.append(value)
        visible = "".join(content_parts)
        payload: dict[str, Any] = {
            "choices": [{"message": {"content": visible or "".join(reasoning_parts)}}]
        }
        if usage is not None:
            payload["usage"] = usage
        return payload



