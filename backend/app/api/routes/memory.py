from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_memory_service
from app.schemas.memory import (
    MemoryAccessLogResponse,
    MemoryCreate,
    MemoryListResponse,
    MemoryRead,
    MemoryShareGrant,
)
from app.services.memory import MemoryService


router = APIRouter(prefix="/api/v1/memories", tags=["memory"])


@router.get("", response_model=MemoryListResponse, summary="캐릭터가 읽을 수 있는 기억 목록 조회")
def list_memories(
    viewer_character_id: Annotated[str, Query(min_length=1, max_length=100)],
    service: Annotated[MemoryService, Depends(get_memory_service)],
) -> MemoryListResponse:
    return service.list_memories(viewer_character_id)


@router.post(
    "",
    response_model=MemoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="기억 생성",
)
def create_memory(
    request: MemoryCreate,
    service: Annotated[MemoryService, Depends(get_memory_service)],
) -> MemoryRead:
    return service.create_memory(request)


@router.delete(
    "/{memory_id}", status_code=status.HTTP_204_NO_CONTENT, summary="기억 삭제(소프트 삭제)"
)
def delete_memory(
    memory_id: UUID,
    service: Annotated[MemoryService, Depends(get_memory_service)],
) -> None:
    service.delete_memory(memory_id)


@router.post(
    "/{memory_id}/share",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="다른 캐릭터에게 기억 읽기 권한 부여",
)
def share_memory(
    memory_id: UUID,
    request: MemoryShareGrant,
    service: Annotated[MemoryService, Depends(get_memory_service)],
) -> None:
    service.share_memory(memory_id, request)


@router.delete(
    "/{memory_id}/share/{character_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="기억 공유 취소",
)
def revoke_memory_share(
    memory_id: UUID,
    character_id: str,
    service: Annotated[MemoryService, Depends(get_memory_service)],
) -> None:
    service.revoke_share(memory_id, character_id)


@router.get(
    "/access-log",
    response_model=MemoryAccessLogResponse,
    summary="메모리 접근 감사 로그 조회",
)
def list_access_log(
    service: Annotated[MemoryService, Depends(get_memory_service)],
    memory_id: Annotated[UUID | None, Query()] = None,
    conversation_id: Annotated[UUID | None, Query()] = None,
) -> MemoryAccessLogResponse:
    return service.list_access_log(memory_id=memory_id, conversation_id=conversation_id)
