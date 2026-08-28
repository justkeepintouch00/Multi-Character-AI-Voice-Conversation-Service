from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.dependencies import get_character_service
from app.schemas.character import CharacterListResponse, CharacterRead, CharacterWrite
from app.services.characters import CharacterService


router = APIRouter(prefix="/api/v1/characters", tags=["characters"])
_ALLOWED_PORTRAIT_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
_MAX_PORTRAIT_BYTES = 10 * 1024 * 1024


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


@router.post(
    "/{character_id}/portrait",
    response_model=CharacterRead,
    summary="캐릭터 프로필 이미지 저장",
)
async def upload_character_portrait(
    character_id: str,
    file: Annotated[UploadFile, File(description="PNG, JPEG 또는 WebP 이미지")],
    service: Annotated[CharacterService, Depends(get_character_service)],
) -> CharacterRead:
    mime_type = file.content_type or ""
    if mime_type not in _ALLOWED_PORTRAIT_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="프로필 이미지는 PNG, JPEG 또는 WebP 파일만 업로드할 수 있습니다.",
        )
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="빈 이미지 파일입니다.")
    if len(content) > _MAX_PORTRAIT_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="이미지는 최대 10MB까지 업로드할 수 있습니다.")
    return service.upload_portrait(character_id, content=content, mime_type=mime_type)
