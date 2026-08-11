from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.services.audio_conversion import AudioConversionError, convert_audio_to_mp3


router = APIRouter(prefix="/api/v1/audio", tags=["audio"])

MAX_AUDIO_BYTES = 20 * 1024 * 1024
CONTENT_TYPE_SUFFIXES = {
    "audio/m4a": ".m4a",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/webm": ".webm",
    "audio/x-m4a": ".m4a",
    "audio/x-wav": ".wav",
}


@router.post(
    "/convert/mp3",
    response_class=Response,
    responses={
        status.HTTP_200_OK: {
            "content": {"audio/mpeg": {}},
            "description": "변환된 MP3 파일",
        }
    },
    summary="개발용 녹음 파일을 MP3로 변환",
)
async def convert_recording_to_mp3(
    file: Annotated[UploadFile, File(description="20MB 이하 음성 파일")],
) -> Response:
    content_type = (file.content_type or "").lower().split(";", 1)[0].strip()
    input_suffix = CONTENT_TYPE_SUFFIXES.get(content_type)
    if input_suffix is None:
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

    try:
        mp3_content = await run_in_threadpool(
            convert_audio_to_mp3,
            content,
            input_suffix,
        )
    except AudioConversionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return Response(
        content=mp3_content,
        media_type="audio/mpeg",
        headers={"Content-Disposition": 'attachment; filename="recording.mp3"'},
    )
