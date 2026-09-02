from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from app.providers.base import (
    AudioStream,
    ProviderConfigurationError,
    ProviderInputError,
    ProviderRequestError,
    ProviderTimeoutError,
)
from app.schemas.scene_plan import SceneEmotion
from app.schemas.speech import AudioFormat, SpeechRequest


TYPECAST_EMOTION_MAP = {
    SceneEmotion.NEUTRAL: "normal",
    SceneEmotion.CALM: "tonedown",
    SceneEmotion.CONCERN: "tonedown",
    SceneEmotion.HAPPY: "happy",
    SceneEmotion.SAD: "sad",
    SceneEmotion.ANGRY: "angry",
    SceneEmotion.WHISPER: "whisper",
    SceneEmotion.ENCOURAGING: "toneup",
    SceneEmotion.SERIOUS: "tonedown",
}


class TypecastTTSProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model: str,
        voice_map: dict[str, str],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.voice_map = voice_map
        self.transport = transport

    async def stream_speech(self, request: SpeechRequest) -> AudioStream:
        if not self.api_key:
            raise ProviderConfigurationError("typecast", "TYPECAST_API_KEY is not configured")

        voice_id = request.voice_id or self.voice_map.get(request.speaker_id)
        if not voice_id or voice_id.startswith("YOUR_"):
            raise ProviderInputError("typecast", "No voice is configured for speaker_id")

        payload = {
            "voice_id": voice_id,
            "text": request.text,
            "model": self.model,
            "language": "kor",
            "prompt": {
                "emotion_type": "preset",
                "emotion_preset": TYPECAST_EMOTION_MAP[request.emotion],
                "emotion_intensity": request.emotion_intensity,
            },
            "output": {"audio_format": request.audio_format.value},
        }
        client = httpx.AsyncClient(
            transport=self.transport,
            timeout=httpx.Timeout(90.0),
        )
        try:
            upstream = await client.send(
                client.build_request(
                    "POST",
                    f"{self.base_url}/v1/text-to-speech/stream",
                    headers={"X-API-KEY": self.api_key},
                    json=payload,
                ),
                stream=True,
            )
        except httpx.TimeoutException as exc:
            await client.aclose()
            raise ProviderTimeoutError("typecast", "TTS request timed out") from exc
        except httpx.RequestError as exc:
            await client.aclose()
            raise ProviderRequestError("typecast", "TTS request failed") from exc

        if upstream.is_error:
            status_code = upstream.status_code
            await upstream.aclose()
            await client.aclose()
            raise ProviderRequestError(
                "typecast", f"TTS upstream returned HTTP {status_code}"
            )

        async def chunks() -> AsyncIterator[bytes]:
            try:
                async for chunk in upstream.aiter_bytes():
                    if chunk:
                        yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        media_type = (
            "audio/mpeg" if request.audio_format == AudioFormat.MP3 else "audio/wav"
        )
        return AudioStream(chunks=chunks(), media_type=media_type)

    async def list_voices(
        self,
        *,
        gender: str | None = None,
        age: str | None = None,
    ) -> list[dict[str, object]]:
        if not self.api_key:
            raise ProviderConfigurationError("typecast", "TYPECAST_API_KEY is not configured")
        params: dict[str, str] = {"model": self.model}
        if gender:
            params["gender"] = gender
        if age:
            params["age"] = age
        async with httpx.AsyncClient(
            transport=self.transport,
            timeout=httpx.Timeout(30.0),
        ) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/v2/voices",
                    headers={"X-API-KEY": self.api_key},
                    params=params,
                )
            except httpx.TimeoutException as exc:
                raise ProviderTimeoutError("typecast", "Voice list request timed out") from exc
            except httpx.RequestError as exc:
                raise ProviderRequestError("typecast", "Voice list request failed") from exc
        if response.is_error:
            raise ProviderRequestError(
                "typecast", f"Voice list upstream returned HTTP {response.status_code}"
            )
        payload = response.json()
        if not isinstance(payload, list):
            raise ProviderRequestError("typecast", "Voice list response has an invalid shape")
        voices: list[dict[str, object]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            voice_id = item.get("voice_id")
            voice_name = item.get("voice_name")
            if not isinstance(voice_id, str) or not isinstance(voice_name, str):
                continue
            voices.append(
                {
                    "voice_id": voice_id,
                    "voice_name": voice_name,
                    "gender": item.get("gender"),
                    "age": item.get("age"),
                    "use_cases": item.get("use_cases", []),
                    "voice_type": item.get("voice_type"),
                }
            )
        return voices

