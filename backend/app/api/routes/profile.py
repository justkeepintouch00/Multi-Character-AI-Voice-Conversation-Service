from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_character_service
from app.schemas.profile import ProfileRead, ProfileUpdate
from app.services.characters import CharacterService


router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


@router.get("", response_model=ProfileRead, summary="사용자 표시 이름 조회")
def get_profile(
    service: Annotated[CharacterService, Depends(get_character_service)],
) -> ProfileRead:
    return service.get_profile()


@router.put("", response_model=ProfileRead, summary="사용자 표시 이름 변경")
def update_profile(
    request: ProfileUpdate,
    service: Annotated[CharacterService, Depends(get_character_service)],
) -> ProfileRead:
    return service.update_profile(request)
