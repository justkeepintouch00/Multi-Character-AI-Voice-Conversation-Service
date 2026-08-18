from __future__ import annotations

from uuid import UUID

from app.providers.base import SceneDirectorProvider
from app.repositories.characters import DevelopmentContext
from app.repositories.conversations import (
    ConversationRepository,
    ConversationSnapshot,
)
from app.repositories.memory import MemoryRecord, MemoryRepository
from app.schemas.conversation import ConversationCreate, ConversationRead
from app.schemas.message import (
    MessageCreate,
    MessageExchangeResponse,
    MessageListResponse,
    ShareSuggestion,
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
            request.memory_sharing_mode,
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

        turns, share_suggestions = await self._generate_turns(
            context=context,
            conversation_id=conversation_id,
            character_ids=conversation.character_ids,
            memory_sharing_mode=conversation.memory_sharing_mode,
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
            share_suggestions=share_suggestions,
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
        memory_sharing_mode: str,
        user_text: str,
        recent_messages: list[RecentMessage],
    ) -> tuple[list[SceneTurn], list[ShareSuggestion]]:
        """Generate 1-2 turns with each speaker getting an independent LLM call.

        The turn-arbiter step (``_order_speakers``) only ever looks at public
        conversation content, never at memory. Each speaker's own call below
        is the only place memory is fetched, and it is fetched for that
        speaker alone via ``MemoryRepository.retrieve`` — the other
        character's private memory is never read into this request.
        """
        if not character_ids:
            return [], []

        first_id, second_id = self._order_speakers(
            character_ids, context.character_profiles, user_text, recent_messages
        )
        first_profile = context.character_profiles[first_id]
        second_profile = (
            context.character_profiles[second_id] if second_id else None
        )

        primary_result, primary_records = await self._request_turn(
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
        share_suggestions = self._build_share_suggestions(
            result=primary_result,
            records=primary_records,
            speaker_id=first_id,
            other_participants=[second_profile] if second_profile else [],
        )
        self._maybe_store_extracted_memory(
            context=context,
            conversation_id=conversation_id,
            character_ids=character_ids,
            memory_sharing_mode=memory_sharing_mode,
            owner_character_id=first_id,
            result=primary_result,
        )

        if second_id is not None and primary_result.needs_second_speaker:
            secondary_recent = [
                *recent_messages,
                RecentMessage(
                    role="CHARACTER",
                    speaker_id=first_id,
                    content=primary_result.text,
                ),
            ]
            secondary_result, secondary_records = await self._request_turn(
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
            share_suggestions.extend(
                self._build_share_suggestions(
                    result=secondary_result,
                    records=secondary_records,
                    speaker_id=second_id,
                    other_participants=[first_profile],
                )
            )
            self._maybe_store_extracted_memory(
                context=context,
                conversation_id=conversation_id,
                character_ids=character_ids,
                memory_sharing_mode=memory_sharing_mode,
                owner_character_id=second_id,
                result=secondary_result,
            )

        return turns, share_suggestions

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
    ) -> tuple[SpeakerTurnResult, list[MemoryRecord]]:
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
                        id=str(record.id),
                        content=record.content,
                        memory_type=record.memory_type,
                        sensitivity=record.sensitivity,
                    )
                    for record in memory_records
                ],
            )
        )
        return result, memory_records

    def _build_share_suggestions(
        self,
        *,
        result: SpeakerTurnResult,
        records: list[MemoryRecord],
        speaker_id: str,
        other_participants: list[SceneCharacter],
    ) -> list[ShareSuggestion]:
        if not result.disclosed_memory_ids or not other_participants:
            return []
        records_by_id = {str(record.id): record for record in records}
        to_character_id = other_participants[0].id
        suggestions: list[ShareSuggestion] = []
        for raw_id in result.disclosed_memory_ids:
            record = records_by_id.get(raw_id)
            # The schema already constrains disclosed_memory_ids to ids that
            # were on this request, but a record lookup miss is tolerated
            # rather than trusted blindly -- never surface a suggestion for
            # a memory we can't independently confirm the speaker actually had.
            if record is None:
                continue
            suggestions.append(
                ShareSuggestion(
                    memory_id=record.id,
                    from_character_id=speaker_id,
                    to_character_id=to_character_id,
                    content_preview=record.content[:120],
                )
            )
        return suggestions

    def _maybe_store_extracted_memory(
        self,
        *,
        context: DevelopmentContext,
        conversation_id: UUID,
        character_ids: list[str],
        memory_sharing_mode: str,
        owner_character_id: str,
        result: SpeakerTurnResult,
    ) -> None:
        if not result.extracted_memory.has_memory:
            return
        content = result.extracted_memory.content.strip()
        if not content:
            return
        readable_by_ids = self._readable_by_for_new_memory(
            memory_sharing_mode=memory_sharing_mode,
            character_ids=character_ids,
            owner_character_id=owner_character_id,
        )
        self.memory_repository.create_memory(
            user_id=context.user_id,
            content=content,
            memory_type="RELATIONSHIP",
            owner_character_instance_id=context.character_instance_ids[
                owner_character_id
            ],
            sensitivity=result.extracted_memory.sensitivity,
            granted_by_user_id=context.user_id,
            readable_by=[
                context.character_instance_ids[character_id]
                for character_id in readable_by_ids
            ],
            source_conversation_id=conversation_id,
        )

    @staticmethod
    def _readable_by_for_new_memory(
        *,
        memory_sharing_mode: str,
        character_ids: list[str],
        owner_character_id: str,
    ) -> list[str]:
        if len(character_ids) < 2:
            return [owner_character_id]
        first_id, second_id = character_ids[0], character_ids[1]
        if memory_sharing_mode == "SHARED":
            return [first_id, second_id]
        if memory_sharing_mode == "FIRST_ONLY" and owner_character_id == first_id:
            return [first_id, second_id]
        if memory_sharing_mode == "SECOND_ONLY" and owner_character_id == second_id:
            return [first_id, second_id]
        return [owner_character_id]

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
            # No character was named explicitly, so default to whoever spoke
            # last continuing the exchange -- the user's next line is far
            # more often a reply/objection to that character than a cue to
            # switch speakers. Forcing alternation here misroutes exactly
            # that case (e.g. "방금 A가 한 말에는 동의가 안 돼" landing on B
            # instead of A). Variety across turns is handled separately by
            # needs_second_speaker, not by flipping the primary responder.
            last_speaker_id = next(
                (
                    message.speaker_id
                    for message in reversed(recent_messages)
                    if message.role == "CHARACTER"
                    and message.speaker_id in character_ids
                ),
                None,
            )
            first_id = last_speaker_id if last_speaker_id is not None else character_ids[0]

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
            memory_sharing_mode=snapshot.memory_sharing_mode,
            created_at=snapshot.created_at,
            updated_at=snapshot.updated_at,
            closed_at=snapshot.closed_at,
        )
