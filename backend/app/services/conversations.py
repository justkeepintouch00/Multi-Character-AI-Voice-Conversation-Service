from __future__ import annotations

from uuid import UUID

from app.providers.base import SceneDirectorProvider
from app.repositories.conversations import (
    ConversationRepository,
    ConversationSnapshot,
)
from app.schemas.conversation import ConversationCreate, ConversationRead
from app.schemas.message import (
    MessageCreate,
    MessageExchangeResponse,
    MessageListResponse,
)
from app.schemas.scene_plan import ScenePlanRequest
from app.services.errors import (
    InvalidResourceInputError,
    ResourceConflictError,
    ResourceNotFoundError,
)


class ConversationService:
    def __init__(
        self,
        repository: ConversationRepository,
        scene_director: SceneDirectorProvider,
    ) -> None:
        self.repository = repository
        self.scene_director = scene_director

    def create_conversation(self, request: ConversationCreate) -> ConversationRead:
        context = self.repository.ensure_development_context()
        unknown_ids = set(request.character_ids) - set(context.character_instance_ids)
        if unknown_ids:
            raise InvalidResourceInputError("지원하지 않는 character_id입니다.")
        snapshot = self.repository.create_conversation(
            context,
            request.mode,
            request.character_ids,
            request.opening_message,
        )
        return self._conversation_read(snapshot)

    def get_conversation(self, conversation_id: UUID) -> ConversationRead:
        context = self.repository.ensure_development_context()
        snapshot = self.repository.get_conversation(context.user_id, conversation_id)
        if snapshot is None:
            raise ResourceNotFoundError("대화를 찾을 수 없습니다.")
        return self._conversation_read(snapshot)

    def complete_conversation(self, conversation_id: UUID) -> ConversationRead:
        context = self.repository.ensure_development_context()
        current = self.repository.get_conversation(context.user_id, conversation_id)
        if current is None:
            raise ResourceNotFoundError("대화를 찾을 수 없습니다.")
        if current.status not in {"ACTIVE", "COMPLETED"}:
            raise ResourceConflictError("현재 상태에서는 대화를 완료할 수 없습니다.")
        snapshot = self.repository.complete_conversation(
            context.user_id, conversation_id
        )
        if snapshot is None:
            raise ResourceNotFoundError("대화를 찾을 수 없습니다.")
        return self._conversation_read(snapshot)

    async def create_message(
        self, conversation_id: UUID, request: MessageCreate
    ) -> MessageExchangeResponse:
        context = self.repository.ensure_development_context()
        conversation = self.repository.get_conversation(
            context.user_id, conversation_id
        )
        if conversation is None:
            raise ResourceNotFoundError("대화를 찾을 수 없습니다.")
        if conversation.status != "ACTIVE":
            raise ResourceConflictError("활성 상태의 대화에만 메시지를 보낼 수 있습니다.")

        user_message = self.repository.add_user_message(
            user_id=context.user_id,
            conversation_id=conversation_id,
            content=request.content,
            input_mode=request.input_mode,
        )
        recent_messages = self.repository.recent_messages(conversation_id)
        if recent_messages and recent_messages[-1].role == "USER":
            recent_messages = recent_messages[:-1]
        scene_plan = await self.scene_director.create_scene_plan(
            ScenePlanRequest(
                user_text=request.content,
                character_ids=conversation.character_ids,
                characters=[
                    context.character_profiles[character_id]
                    for character_id in conversation.character_ids
                ],
                recent_messages=recent_messages,
            )
        )
        assistant_messages = self.repository.save_scene_result(
            context=context,
            conversation_id=conversation_id,
            triggering_message_id=user_message.id,
            plan=scene_plan,
        )
        return MessageExchangeResponse(
            user_message=user_message,
            scene_plan=scene_plan,
            assistant_messages=assistant_messages,
        )

    def list_messages(
        self, conversation_id: UUID, limit: int
    ) -> MessageListResponse:
        context = self.repository.ensure_development_context()
        conversation = self.repository.get_conversation(
            context.user_id, conversation_id
        )
        if conversation is None:
            raise ResourceNotFoundError("대화를 찾을 수 없습니다.")
        return MessageListResponse(
            items=self.repository.list_messages(conversation_id, limit)
        )

    @staticmethod
    def _conversation_read(snapshot: ConversationSnapshot) -> ConversationRead:
        return ConversationRead(
            id=snapshot.id,
            mode=snapshot.mode,
            status=snapshot.status,
            character_ids=snapshot.character_ids,
            created_at=snapshot.created_at,
            updated_at=snapshot.updated_at,
            closed_at=snapshot.closed_at,
        )
