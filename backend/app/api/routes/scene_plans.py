from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_scene_director_provider
from app.providers.base import SceneDirectorProvider
from app.schemas.speaker_turn import SpeakerTurnRequest, SpeakerTurnResult


router = APIRouter(prefix="/api/v1/speaker-turns", tags=["scene-director"])


@router.post(
    "",
    response_model=SpeakerTurnResult,
    status_code=status.HTTP_200_OK,
    summary="단일 캐릭터의 발화 한 턴 생성 (Scene Director 디버그용)",
)
async def create_speaker_turn(
    request: SpeakerTurnRequest,
    provider: Annotated[SceneDirectorProvider, Depends(get_scene_director_provider)],
) -> SpeakerTurnResult:
    return await provider.create_speaker_turn(request)
