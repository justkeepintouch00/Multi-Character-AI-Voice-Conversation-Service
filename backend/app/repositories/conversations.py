from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.db.models import (
    CharacterInstance,
    CharacterTemplate,
    Conversation,
    ConversationParticipant,
    Message,
    ScenePlan as ScenePlanModel,
)
from app.repositories.characters import DevelopmentContext, SQLAlchemyCharacterRepository
from app.schemas.conversation import ConversationOpeningMessage
from app.schemas.message import MessageRead
from app.schemas.scene_plan import RecentMessage, ScenePlan


@dataclass(frozen=True, slots=True)
class ConversationSnapshot:
    id: UUID
    mode: str
    status: str
    character_ids: list[str]
    memory_sharing_mode: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class ConversationRepository(Protocol):
    def ensure_development_context(self) -> DevelopmentContext: ...

    def create_conversation(
        self,
        context: DevelopmentContext,
        mode: str,
        character_ids: list[str],
        opening_message: ConversationOpeningMessage | None = None,
        memory_sharing_mode: str = "NONE",
    ) -> ConversationSnapshot: ...

    def get_conversation(
        self, user_id: UUID, conversation_id: UUID
    ) -> ConversationSnapshot | None: ...

    def complete_conversation(
        self, user_id: UUID, conversation_id: UUID
    ) -> ConversationSnapshot | None: ...

    def add_user_message(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        input_mode: str,
    ) -> MessageRead: ...

    def recent_messages(
        self, conversation_id: UUID, limit: int = 12
    ) -> list[RecentMessage]: ...

    def save_scene_result(
        self,
        *,
        context: DevelopmentContext,
        conversation_id: UUID,
        triggering_message_id: UUID,
        plan: ScenePlan,
    ) -> list[MessageRead]: ...

    def list_messages(self, conversation_id: UUID, limit: int) -> list[MessageRead]: ...


class SQLAlchemyConversationRepository:
    def __init__(
        self,
        session: Session,
        *,
        development_user_external_id: str,
        development_user_display_name: str,
    ) -> None:
        self.session = session
        self.development_user_external_id = development_user_external_id
        self.development_user_display_name = development_user_display_name

    def ensure_development_context(self) -> DevelopmentContext:
        return SQLAlchemyCharacterRepository(
            self.session,
            development_user_external_id=self.development_user_external_id,
            development_user_display_name=self.development_user_display_name,
        ).ensure_development_context()

    def create_conversation(
        self,
        context: DevelopmentContext,
        mode: str,
        character_ids: list[str],
        opening_message: ConversationOpeningMessage | None = None,
        memory_sharing_mode: str = "NONE",
    ) -> ConversationSnapshot:
        conversation = Conversation(
            user_id=context.user_id,
            mode=mode,
            status="ACTIVE",
            memory_sharing_mode=memory_sharing_mode,
        )
        self.session.add(conversation)
        self.session.flush()
        for display_order, public_id in enumerate(character_ids):
            self.session.add(
                ConversationParticipant(
                    conversation_id=conversation.id,
                    character_instance_id=context.character_instance_ids[public_id],
                    display_order=display_order,
                    participant_role="ACTIVE",
                )
            )
        if opening_message is not None:
            self.session.add(
                Message(
                    conversation_id=conversation.id,
                    created_at=datetime.now(timezone.utc),
                    speaker_type="CHARACTER",
                    speaker_user_id=None,
                    speaker_character_instance_id=context.character_instance_ids[
                        opening_message.speaker_id
                    ],
                    content=opening_message.content,
                    input_mode="SYSTEM",
                    finalized=True,
                    interrupted=False,
                )
            )
        self.session.commit()
        self.session.refresh(conversation)
        return self._conversation_snapshot(conversation)

    def get_conversation(
        self, user_id: UUID, conversation_id: UUID
    ) -> ConversationSnapshot | None:
        conversation = self.session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        return self._conversation_snapshot(conversation) if conversation else None

    def complete_conversation(
        self, user_id: UUID, conversation_id: UUID
    ) -> ConversationSnapshot | None:
        conversation = self.session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        if conversation is None:
            return None
        if conversation.status == "ACTIVE":
            conversation.status = "COMPLETED"
            conversation.closed_at = datetime.now(timezone.utc)
            self.session.commit()
            self.session.refresh(conversation)
        return self._conversation_snapshot(conversation)

    def add_user_message(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        input_mode: str,
    ) -> MessageRead:
        message = Message(
            conversation_id=conversation_id,
            created_at=datetime.now(timezone.utc),
            speaker_type="USER",
            speaker_user_id=user_id,
            speaker_character_instance_id=None,
            content=content,
            input_mode=input_mode,
            finalized=True,
            interrupted=False,
        )
        self.session.add(message)
        self.session.commit()
        self.session.refresh(message)
        return self._message_read(message, {})

    def recent_messages(
        self, conversation_id: UUID, limit: int = 12
    ) -> list[RecentMessage]:
        messages = list(
            self.session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(
                    Message.created_at.desc(),
                    case((Message.speaker_type == "CHARACTER", Message.scene_turn_index), else_=0).desc(),
                    Message.id.desc(),
                )
                .limit(limit)
            )
        )
        messages.reverse()
        character_map = self._character_public_id_map(conversation_id)
        return [
            RecentMessage(
                role=("USER" if message.speaker_type == "USER" else "CHARACTER"),
                speaker_id=(
                    character_map.get(message.speaker_character_instance_id)
                    if message.speaker_type == "CHARACTER"
                    else None
                ),
                content=message.content,
            )
            for message in messages
            if message.speaker_type in {"USER", "CHARACTER"}
        ]

    def save_scene_result(
        self,
        *,
        context: DevelopmentContext,
        conversation_id: UUID,
        triggering_message_id: UUID,
        plan: ScenePlan,
    ) -> list[MessageRead]:
        scene_plan = ScenePlanModel(
            conversation_id=conversation_id,
            triggering_message_id=triggering_message_id,
            can_ai_speak=bool(plan.turns),
            internal_step_count=plan.max_internal_turns,
            visible_turn_count=len(plan.turns),
            return_turn_to=plan.return_turn_to,
            plan_json=plan.model_dump(mode="json"),
            fallback_reason=None,
        )
        self.session.add(scene_plan)
        self.session.flush()

        messages: list[Message] = []
        created_at = datetime.now(timezone.utc)
        for turn_index, turn in enumerate(plan.turns):
            message = Message(
                conversation_id=conversation_id,
                created_at=created_at,
                speaker_type="CHARACTER",
                speaker_user_id=None,
                speaker_character_instance_id=context.character_instance_ids[
                    turn.speaker_id
                ],
                scene_plan_id=scene_plan.id,
                scene_turn_index=turn_index,
                content=turn.text,
                input_mode="SYSTEM",
                finalized=True,
                interrupted=False,
            )
            self.session.add(message)
            messages.append(message)
        self.session.commit()
        for message in messages:
            self.session.refresh(message)
        reverse_map = {
            instance_id: public_id
            for public_id, instance_id in context.character_instance_ids.items()
        }
        return [self._message_read(message, reverse_map) for message in messages]

    def list_messages(self, conversation_id: UUID, limit: int) -> list[MessageRead]:
        messages = list(
            self.session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(
                    Message.created_at.asc(),
                    case((Message.speaker_type == "USER", 0), else_=1).asc(),
                    case((Message.speaker_type == "CHARACTER", Message.scene_turn_index), else_=0).asc(),
                    Message.id.asc(),
                )
                .limit(limit)
            )
        )
        character_map = self._character_public_id_map(conversation_id)
        return [self._message_read(message, character_map) for message in messages]

    def _conversation_snapshot(
        self, conversation: Conversation
    ) -> ConversationSnapshot:
        character_map = self._character_public_id_map(conversation.id)
        participant_rows = self.session.execute(
            select(
                ConversationParticipant.character_instance_id,
                ConversationParticipant.display_order,
            )
            .where(ConversationParticipant.conversation_id == conversation.id)
            .order_by(ConversationParticipant.display_order.asc())
        )
        character_ids = [
            character_map[instance_id]
            for instance_id, _display_order in participant_rows
            if instance_id in character_map
        ]
        return ConversationSnapshot(
            id=conversation.id,
            mode=conversation.mode,
            status=conversation.status,
            character_ids=character_ids,
            memory_sharing_mode=conversation.memory_sharing_mode,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            closed_at=conversation.closed_at,
        )

    def _character_public_id_map(self, conversation_id: UUID) -> dict[UUID, str]:
        context = self.ensure_development_context()
        known_public_ids = {
            instance_id: public_id
            for public_id, instance_id in context.character_instance_ids.items()
        }
        rows = self.session.execute(
            select(CharacterInstance.id, CharacterTemplate.name)
            .join(
                ConversationParticipant,
                ConversationParticipant.character_instance_id == CharacterInstance.id,
            )
            .join(
                CharacterTemplate,
                CharacterTemplate.id == CharacterInstance.template_id,
            )
            .where(ConversationParticipant.conversation_id == conversation_id)
        )
        result: dict[UUID, str] = {}
        for instance_id, _name in rows:
            result[instance_id] = known_public_ids.get(instance_id, str(instance_id))
        return result

    @staticmethod
    def _message_read(
        message: Message, character_map: dict[UUID, str]
    ) -> MessageRead:
        speaker_id = None
        if message.speaker_type == "CHARACTER":
            speaker_id = character_map.get(message.speaker_character_instance_id)
        return MessageRead(
            id=message.id,
            speaker_type=message.speaker_type,
            speaker_id=speaker_id,
            content=message.content,
            input_mode=message.input_mode,
            finalized=message.finalized,
            interrupted=message.interrupted,
            created_at=message.created_at,
        )
