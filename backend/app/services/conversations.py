from __future__ import annotations

from uuid import UUID

from app.providers.base import SceneDirectorProvider
from app.repositories.characters import DevelopmentContext
from app.repositories.conversations import (
    ConversationRepository,
    ConversationSnapshot,
)
from app.repositories.memory import MemoryRepository
from app.schemas.conversation import ConversationCreate, ConversationRead
from app.schemas.message import (
    MessageCreate,
    MessageExchangeResponse,
    MessageListResponse,
)
from app.schemas.scene_plan import RecentMessage, SceneCharacter, ScenePlan, SceneTurn
from app.schemas.speaker_turn import (
    MemoryContextItem,
    SpeakerTurnRequest,
    SpeakerTurnResult,
)
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
        memory_repository: MemoryRepository,
    ) -> None:
        self.repository = repository
        self.scene_director = scene_director
        self.memory_repository = memory_repository

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

        turns = await self._generate_turns(
            context=context,
            conversation_id=conversation_id,
            character_ids=conversation.character_ids,
            user_text=request.content,
            recent_messages=recent_messages,
        )
        plan = ScenePlan(
            scene_action="CHARACTER_SEQUENCE",
            turns=turns,
            return_turn_to="USER",
            max_internal_turns=len(turns),
        )
        assistant_messages = self.repository.save_scene_result(
            context=context,
            conversation_id=conversation_id,
            triggering_message_id=user_message.id,
            plan=plan,
        )
        return MessageExchangeResponse(
            user_message=user_message,
            scene_plan=plan,
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

    async def _generate_turns(
        self,
        *,
        context: DevelopmentContext,
        conversation_id: UUID,
        character_ids: list[str],
        user_text: str,
        recent_messages: list[RecentMessage],
    ) -> list[SceneTurn]:
        """Generate 1-2 turns with each speaker getting an independent LLM call.

        The turn-arbiter step (``_order_speakers``) only ever looks at public
        conversation content, never at memory. Each speaker's own call below
        is the only place memory is fetched, and it is fetched for that
        speaker alone via ``MemoryRepository.retrieve`` — the other
        character's private memory is never read into this request.
        """
        if not character_ids:
            return []

        first_id, second_id = self._order_speakers(
            character_ids, context.character_profiles, user_text, recent_messages
        )
        first_profile = context.character_profiles[first_id]
        second_profile = (
            context.character_profiles[second_id] if second_id else None
        )

        primary_result = await self._request_turn(
            role="PRIMARY",
            context=context,
            conversation_id=conversation_id,
            user_text=user_text,
            speaker_id=first_id,
            speaker_profile=first_profile,
            other_participants=[second_profile] if second_profile else [],
            recent_messages=recent_messages,
        )
        turns = [self._to_scene_turn(primary_result)]

        if second_id is not None and primary_result.needs_second_speaker:
            secondary_recent = [
                *recent_messages,
                RecentMessage(
                    role="CHARACTER",
                    speaker_id=first_id,
                    content=primary_result.text,
                ),
            ]
            secondary_result = await self._request_turn(
                role="SECONDARY",
                context=context,
                conversation_id=conversation_id,
                user_text=user_text,
                speaker_id=second_id,
                speaker_profile=context.character_profiles[second_id],
                other_participants=[first_profile],
                recent_messages=secondary_recent,
            )
            turns.append(self._to_scene_turn(secondary_result))

        return turns

    async def _request_turn(
        self,
        *,
        role: str,
        context: DevelopmentContext,
        conversation_id: UUID,
        user_text: str,
        speaker_id: str,
        speaker_profile: SceneCharacter,
        other_participants: list[SceneCharacter],
        recent_messages: list[RecentMessage],
    ) -> SpeakerTurnResult:
        memory_records = self.memory_repository.retrieve(
            user_id=context.user_id,
            viewer_character_instance_id=context.character_instance_ids[speaker_id],
            conversation_id=conversation_id,
        )
        result = await self.scene_director.create_speaker_turn(
            SpeakerTurnRequest(
                role=role,
                user_text=user_text,
                speaker=speaker_profile,
                other_participants=other_participants,
                recent_messages=recent_messages,
                memory_context=[
                    MemoryContextItem(
                        content=record.content,
                        memory_type=record.memory_type,
                        sensitivity=record.sensitivity,
                    )
                    for record in memory_records
                ],
            )
        )
        return result

    @staticmethod
    def _order_speakers(
        character_ids: list[str],
        character_profiles: dict[str, SceneCharacter],
        user_text: str,
        recent_messages: list[RecentMessage],
    ) -> tuple[str, str | None]:
        if len(character_ids) == 1:
            return character_ids[0], None

        named_ids = [
            character_id
            for character_id in character_ids
            if character_profiles[character_id].name
            and character_profiles[character_id].name in user_text
        ]
        if len(named_ids) == 1:
            first_id = named_ids[0]
        else:
            last_speaker_id = next(
                (
                    message.speaker_id
                    for message in reversed(recent_messages)
                    if message.role == "CHARACTER"
                    and message.speaker_id in character_ids
                ),
                None,
            )
            if last_speaker_id is not None:
                others = [
                    character_id
                    for character_id in character_ids
                    if character_id != last_speaker_id
                ]
                first_id = others[0] if others else character_ids[0]
            else:
                first_id = character_ids[0]

        second_id = next(
            character_id for character_id in character_ids if character_id != first_id
        )
        return first_id, second_id

    @staticmethod
    def _to_scene_turn(result: SpeakerTurnResult) -> SceneTurn:
        return SceneTurn(
            speaker_id=result.speaker_id,
            to=result.to,
            emotion=result.emotion,
            text=result.text,
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
