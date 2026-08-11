from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_conversation_service
from app.schemas.conversation import ConversationCreate, ConversationRead
from app.schemas.message import (
    MessageCreate,
    MessageExchangeResponse,
    MessageListResponse,
)
from app.services.conversations import ConversationService


router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.post(
    "",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
    summary="개발용 TALK 대화 생성",
)
def create_conversation(
    request: ConversationCreate,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> ConversationRead:
    return service.create_conversation(request)


@router.get(
    "/{conversation_id}",
    response_model=ConversationRead,
    summary="대화 조회",
)
def get_conversation(
    conversation_id: UUID,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> ConversationRead:
    return service.get_conversation(conversation_id)


@router.post(
    "/{conversation_id}/complete",
    response_model=ConversationRead,
    summary="대화 완료",
)
def complete_conversation(
    conversation_id: UUID,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> ConversationRead:
    return service.complete_conversation(conversation_id)


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageExchangeResponse,
    summary="사용자 메시지 저장 및 Scene Director 응답 생성",
)
async def create_message(
    conversation_id: UUID,
    request: MessageCreate,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> MessageExchangeResponse:
    return await service.create_message(conversation_id, request)


@router.get(
    "/{conversation_id}/messages",
    response_model=MessageListResponse,
    summary="대화 메시지 목록",
)
def list_messages(
    conversation_id: UUID,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> MessageListResponse:
    return service.list_messages(conversation_id, limit)
