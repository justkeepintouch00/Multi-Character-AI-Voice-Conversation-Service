from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_tts_provider
from app.providers.base import TTSProvider
from app.schemas.speech import SpeechRequest


router = APIRouter(prefix="/api/v1/tts", tags=["text-to-speech"])


@router.post(
    "/stream",
    response_class=StreamingResponse,
    summary="캐릭터 대사를 스트리밍 음성으로 변환",
)
async def stream_speech(
    request: SpeechRequest,
    provider: Annotated[TTSProvider, Depends(get_tts_provider)],
) -> StreamingResponse:
    audio = await provider.stream_speech(request)
    return StreamingResponse(
        audio.chunks,
        media_type=audio.media_type,
        headers={"Cache-Control": "no-store"},
    )
