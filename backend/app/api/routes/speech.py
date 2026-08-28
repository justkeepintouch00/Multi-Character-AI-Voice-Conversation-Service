import logging
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_tts_provider
from app.observability import METRICS, log_event
from app.providers.base import TTSProvider
from app.schemas.speech import SpeechRequest, TypecastVoiceRead


router = APIRouter(prefix="/api/v1/tts", tags=["text-to-speech"])


@router.get("/voices", response_model=list[TypecastVoiceRead], summary="선택 가능한 Typecast 음성 목록")
async def list_typecast_voices(
    provider: Annotated[TTSProvider, Depends(get_tts_provider)],
    gender: str | None = Query(default=None, pattern="^(male|female)$"),
    age: str | None = Query(
        default=None,
        pattern="^(child|teenager|young_adult|middle_age|elder)$",
    ),
) -> list[TypecastVoiceRead]:
    list_voices = getattr(provider, "list_voices", None)
    if list_voices is None:
        raise RuntimeError("Configured TTS provider does not support voice listing")
    voices = await list_voices(gender=gender, age=age)
    return [TypecastVoiceRead.model_validate(voice) for voice in voices]
@router.post(
    "/stream",
    response_class=StreamingResponse,
    summary="캐릭터 대사를 스트리밍 음성으로 변환",
)
async def stream_speech(
    request: SpeechRequest,
    provider: Annotated[TTSProvider, Depends(get_tts_provider)],
) -> StreamingResponse:
    provider_name = getattr(provider, "provider_name", "typecast")
    setup_started = perf_counter()
    try:
        audio = await provider.stream_speech(request)
    except Exception as exc:
        setup_duration_ms = (perf_counter() - setup_started) * 1000
        METRICS.increment(
            "tts_requests_total", provider=provider_name, status="failed_setup"
        )
        METRICS.observe(
            "tts_setup_duration_ms",
            setup_duration_ms,
            provider=provider_name,
            status="failed",
        )
        log_event(
            "tts_request_failed",
            level=logging.ERROR,
            provider=provider_name,
            speaker_id=request.speaker_id,
            phase="setup",
            duration_ms=round(setup_duration_ms, 3),
            error_type=type(exc).__name__,
        )
        raise
    setup_duration_ms = (perf_counter() - setup_started) * 1000
    METRICS.observe(
        "tts_setup_duration_ms",
        setup_duration_ms,
        provider=provider_name,
        status="success",
    )

    async def observed_chunks():
        stream_started = perf_counter()
        byte_count = 0
        stream_status = "success"
        try:
            async for chunk in audio.chunks:
                byte_count += len(chunk)
                yield chunk
        except Exception as exc:
            stream_status = "failed_stream"
            log_event(
                "tts_request_failed",
                level=logging.ERROR,
                provider=provider_name,
                speaker_id=request.speaker_id,
                phase="stream",
                error_type=type(exc).__name__,
            )
            raise
        finally:
            stream_duration_ms = (perf_counter() - stream_started) * 1000
            METRICS.increment(
                "tts_requests_total", provider=provider_name, status=stream_status
            )
            METRICS.observe(
                "tts_stream_duration_ms",
                stream_duration_ms,
                provider=provider_name,
                status=stream_status,
            )
            METRICS.observe(
                "tts_stream_bytes",
                byte_count,
                provider=provider_name,
                status=stream_status,
            )
            log_event(
                "tts_request_completed",
                provider=provider_name,
                speaker_id=request.speaker_id,
                status=stream_status,
                setup_duration_ms=round(setup_duration_ms, 3),
                stream_duration_ms=round(stream_duration_ms, 3),
                byte_count=byte_count,
            )

    return StreamingResponse(
        observed_chunks(),
        media_type=audio.media_type,
        headers={"Cache-Control": "no-store"},
    )

