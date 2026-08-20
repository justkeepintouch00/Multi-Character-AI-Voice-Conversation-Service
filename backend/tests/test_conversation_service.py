from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.repositories.conversations import (
    ConversationSnapshot,
    DevelopmentContext,
)
from app.schemas.conversation import ConversationCreate
from app.schemas.message import MessageCreate, MessageRead
from app.schemas.scene_plan import RecentMessage, ScenePlan, ScenePlanRequest
from app.schemas.scene_plan import SceneCharacter
from app.services.conversations import ConversationService
from app.services.errors import InvalidResourceInputError, ResourceConflictError


NOW = datetime.now(timezone.utc)


class FakeRepository:
    def __init__(self) -> None:
        self.user_id = uuid4()
        self.conversation_id = uuid4()
        self.status = "ACTIVE"
        self.saved_user_message: MessageRead | None = None
        self.saved_plan: ScenePlan | None = None
        self.context = DevelopmentContext(
            user_id=self.user_id,
            character_instance_ids={
                "character_a": uuid4(),
                "character_b": uuid4(),
            },
            character_profiles={
                "character_a": SceneCharacter(
                    id="character_a",
                    name="루미",
                    concept="사용자의 말을 차분하게 듣고 맥락을 기억하는 대화 캐릭터입니다.",
                    persona="차분하게 반응한다.",
                    traits=["차분한"],
                ),
                "character_b": SceneCharacter(
                    id="character_b",
                    name="하루",
                    concept="앞 캐릭터의 말을 듣고 다른 관점을 자연스럽게 이어가는 캐릭터입니다.",
                    persona="솔직하고 자연스럽게 말한다.",
                    traits=["솔직한"],
                ),
            },
        )

    def ensure_development_context(self) -> DevelopmentContext:
        return self.context

    def create_conversation(
        self,
        context: DevelopmentContext,
        mode: str,
        character_ids: list[str],
        opening_message=None,
    ) -> ConversationSnapshot:
        assert context == self.context
        del opening_message
        return self._snapshot(mode=mode, character_ids=character_ids)

    def get_conversation(
        self, user_id: UUID, conversation_id: UUID
    ) -> ConversationSnapshot | None:
        if user_id != self.user_id or conversation_id != self.conversation_id:
            return None
        return self._snapshot()

    def complete_conversation(
        self, user_id: UUID, conversation_id: UUID
    ) -> ConversationSnapshot | None:
        if user_id != self.user_id or conversation_id != self.conversation_id:
            return None
        self.status = "COMPLETED"
        return self._snapshot()

    def add_user_message(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        input_mode: str,
    ) -> MessageRead:
        assert user_id == self.user_id
        assert conversation_id == self.conversation_id
        self.saved_user_message = MessageRead(
            id=uuid4(),
            speaker_type="USER",
            speaker_id=None,
            content=content,
            input_mode=input_mode,
            finalized=True,
            interrupted=False,
            created_at=NOW,
        )
        return self.saved_user_message

    def recent_messages(
        self, conversation_id: UUID, limit: int = 12
    ) -> list[RecentMessage]:
        assert conversation_id == self.conversation_id
        assert limit == 12
        return [
            RecentMessage(
                role="CHARACTER",
                speaker_id="character_a",
                content="천천히 이야기해도 괜찮아.",
            ),
            RecentMessage(
                role="USER",
                speaker_id=None,
                content=self.saved_user_message.content,
            ),
        ]

    def save_scene_result(
        self,
        *,
        context: DevelopmentContext,
        conversation_id: UUID,
        triggering_message_id: UUID,
        plan: ScenePlan,
    ) -> list[MessageRead]:
        assert context == self.context
        assert conversation_id == self.conversation_id
        assert triggering_message_id == self.saved_user_message.id
        self.saved_plan = plan
        return [
            MessageRead(
                id=uuid4(),
                speaker_type="CHARACTER",
                speaker_id=turn.speaker_id,
                content=turn.text,
                input_mode="SYSTEM",
                finalized=True,
                interrupted=False,
                created_at=NOW,
            )
            for turn in plan.turns
        ]

    def list_messages(self, conversation_id: UUID, limit: int) -> list[MessageRead]:
        assert conversation_id == self.conversation_id
        assert limit == 50
        return [self.saved_user_message] if self.saved_user_message else []

    def _snapshot(
        self,
        *,
        mode: str = "TALK",
        character_ids: list[str] | None = None,
    ) -> ConversationSnapshot:
        return ConversationSnapshot(
            id=self.conversation_id,
            mode=mode,
            status=self.status,
            character_ids=character_ids or ["character_a", "character_b"],
            created_at=NOW,
            updated_at=NOW,
            closed_at=NOW if self.status == "COMPLETED" else None,
        )


class FakeSceneDirector:
    def __init__(self) -> None:
        self.last_request: ScenePlanRequest | None = None

    async def create_scene_plan(self, request: ScenePlanRequest) -> ScenePlan:
        self.last_request = request
        return ScenePlan.model_validate(
            {
                "scene_action": "CHARACTER_SEQUENCE",
                "turns": [
                    {
                        "speaker_id": "character_a",
                        "to": "USER",
                        "emotion": "concern",
                        "text": "그 일이 계속 마음에 남아 있었구나.",
                    }
                ],
                "return_turn_to": "USER",
                "max_internal_turns": 1,
            }
        )


def test_create_talk_conversation() -> None:
    repository = FakeRepository()
    service = ConversationService(repository, FakeSceneDirector())

    result = service.create_conversation(
        ConversationCreate(character_ids=["character_a", "character_b"])
    )

    assert result.status == "ACTIVE"
    assert result.character_ids == ["character_a", "character_b"]


def test_reject_unknown_character_before_database_write() -> None:
    repository = FakeRepository()
    service = ConversationService(repository, FakeSceneDirector())

    with pytest.raises(InvalidResourceInputError):
        service.create_conversation(
            ConversationCreate(character_ids=["unknown_character"])
        )


def test_message_is_saved_then_scene_result_is_created() -> None:
    repository = FakeRepository()
    scene_director = FakeSceneDirector()
    service = ConversationService(repository, scene_director)

    result = asyncio.run(
        service.create_message(
            repository.conversation_id,
            MessageCreate(content="오늘 회사에서 조금 힘들었어."),
        )
    )

    assert repository.saved_user_message is not None
    assert repository.saved_plan is not None
    assert result.user_message.content == "오늘 회사에서 조금 힘들었어."
    assert result.assistant_messages[0].speaker_id == "character_a"
    assert len(scene_director.last_request.recent_messages) == 1
    assert scene_director.last_request.recent_messages[0].role == "CHARACTER"
    assert scene_director.last_request.characters[0].name == "루미"


def test_completed_conversation_rejects_new_message() -> None:
    repository = FakeRepository()
    repository.status = "COMPLETED"
    service = ConversationService(repository, FakeSceneDirector())

    with pytest.raises(ResourceConflictError):
        asyncio.run(
            service.create_message(
                repository.conversation_id,
                MessageCreate(content="완료된 대화에 보낼 메시지"),
            )
        )
