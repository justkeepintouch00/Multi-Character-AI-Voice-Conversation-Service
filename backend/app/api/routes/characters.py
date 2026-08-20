from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_character_service
from app.schemas.character import CharacterListResponse, CharacterRead, CharacterWrite
from app.services.characters import CharacterService


router = APIRouter(prefix="/api/v1/characters", tags=["characters"])


@router.get("", response_model=CharacterListResponse, summary="캐릭터 목록 조회")
def list_characters(
    service: Annotated[CharacterService, Depends(get_character_service)],
) -> CharacterListResponse:
    return service.list_characters()


@router.get("/{character_id}", response_model=CharacterRead, summary="캐릭터 조회")
def get_character(
    character_id: str,
    service: Annotated[CharacterService, Depends(get_character_service)],
) -> CharacterRead:
    return service.get_character(character_id)


@router.post(
    "",
    response_model=CharacterRead,
    status_code=status.HTTP_201_CREATED,
    summary="캐릭터 생성",
)
def create_character(
    request: CharacterWrite,
    service: Annotated[CharacterService, Depends(get_character_service)],
) -> CharacterRead:
    return service.create_character(request)


@router.put(
    "/{character_id}", response_model=CharacterRead, summary="캐릭터 새 버전 저장"
)
def update_character(
    character_id: str,
    request: CharacterWrite,
    service: Annotated[CharacterService, Depends(get_character_service)],
) -> CharacterRead:
    return service.update_character(character_id, request)
