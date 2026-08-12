from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.dependencies import get_stt_provider
from app.providers.base import STTProvider
from app.schemas.transcription import (
    TranscriptionResponse,
    TranscriptionSegmentResponse,
)


router = APIRouter(prefix="/api/v1/stt", tags=["speech-to-text"])

MAX_AUDIO_BYTES = 20 * 1024 * 1024
SUPPORTED_AUDIO_TYPES = {
    "audio/m4a",
    "audio/mp4",
    "audio/mpeg",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
    "audio/x-m4a",
    "audio/x-wav",
}


@router.post(
    "/transcriptions",
    response_model=TranscriptionResponse,
    response_model_exclude_none=True,
    response_model_exclude_defaults=True,
    summary="녹음 파일을 텍스트로 변환",
)
async def create_transcription(
    file: Annotated[UploadFile, File(description="20MB 이하 음성 파일")],
    provider: Annotated[STTProvider, Depends(get_stt_provider)],
    language: Annotated[str, Form(min_length=2, max_length=10)] = "ko",
) -> TranscriptionResponse:
    content_type = (file.content_type or "").lower().split(";", 1)[0].strip()
    if content_type not in SUPPORTED_AUDIO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="지원하지 않는 오디오 형식입니다.",
        )

    content = await file.read(MAX_AUDIO_BYTES + 1)
    await file.close()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="빈 오디오 파일입니다.",
        )
    if len(content) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="오디오 파일은 20MB 이하여야 합니다.",
        )

    result = await provider.transcribe(
        filename=file.filename or "recording.webm",
        content=content,
        content_type=content_type,
        language=language.lower(),
    )
    segments = (
        [
            TranscriptionSegmentResponse(
                id=segment.id,
                start_seconds=segment.start_seconds,
                end_seconds=segment.end_seconds,
                text=segment.text,
                avg_logprob=segment.avg_logprob,
                compression_ratio=segment.compression_ratio,
                no_speech_prob=segment.no_speech_prob,
            )
            for segment in result.segments
        ]
        or None
    )
    return TranscriptionResponse(
        text=result.text,
        language=result.language,
        duration_seconds=result.duration_seconds,
        segments=segments,
        model=result.model,
        fallback_used=result.fallback_used,
        fallback_reason=result.fallback_reason,
        primary_model=result.primary_model,
        primary_text=result.primary_text,
        primary_avg_logprob=result.primary_avg_logprob,
        language_mismatch=result.language_mismatch,
    )
