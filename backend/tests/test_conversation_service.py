from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.repositories.characters import DevelopmentContext
from app.repositories.conversations import ConversationSnapshot
from app.repositories.memory import MemoryRecord
from app.schemas.conversation import ConversationCreate
from app.schemas.message import MessageCreate, MessageRead
from app.schemas.scene_plan import RecentMessage, SceneCharacter, ScenePlan
from app.schemas.speaker_turn import SpeakerTurnRequest, SpeakerTurnResult
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
        self.memory_sharing_mode = "NONE"
        self.character_ids = ["character_a", "character_b"]
        self.character_instance_ids = {
            "character_a": uuid4(),
            "character_b": uuid4(),
        }
        self.context = DevelopmentContext(
            user_id=self.user_id,
            character_instance_ids=self.character_instance_ids,
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
        memory_sharing_mode: str = "NONE",
    ) -> ConversationSnapshot:
        assert context == self.context
        del opening_message
        self.memory_sharing_mode = memory_sharing_mode
        return self._snapshot(mode=mode, character_ids=character_ids)

    def get_conversation(
        self, user_id: UUID, conversation_id: UUID
    ) -> ConversationSnapshot | None:
        if user_id != self.user_id or conversation_id != self.conversation_id:
            return None
        return self._snapshot(character_ids=self.character_ids)

    def complete_conversation(
        self, user_id: UUID, conversation_id: UUID
    ) -> ConversationSnapshot | None:
        if user_id != self.user_id or conversation_id != self.conversation_id:
            return None
        self.status = "COMPLETED"
        return self._snapshot(character_ids=self.character_ids)

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
                speaker_id="character_b",
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
            memory_sharing_mode=self.memory_sharing_mode,
            created_at=NOW,
            updated_at=NOW,
            closed_at=NOW if self.status == "COMPLETED" else None,
        )


class FakeMemoryRepository:
    """Returns a distinct private memory per viewer, like a real ACL-scoped store."""

    def __init__(self, *, memories_by_viewer: dict[UUID, list[MemoryRecord]]) -> None:
        self.memories_by_viewer = memories_by_viewer
        self.requested_viewers: list[UUID] = []
        self.created_memories: list[dict] = []

    def retrieve(
        self,
        *,
        user_id: UUID,
        viewer_character_instance_id: UUID,
        limit: int = 8,
        conversation_id: UUID | None = None,
        scene_plan_id: UUID | None = None,
    ) -> list[MemoryRecord]:
        self.requested_viewers.append(viewer_character_instance_id)
        return self.memories_by_viewer.get(viewer_character_instance_id, [])

    def create_memory(self, **kwargs) -> MemoryRecord:
        self.created_memories.append(kwargs)
        return MemoryRecord(
            id=uuid4(),
            content=kwargs["content"],
            memory_type=kwargs["memory_type"],
            sensitivity=kwargs["sensitivity"],
            owner_character_instance_id=kwargs["owner_character_instance_id"],
        )


class FakeSceneDirector:
    def __init__(
        self,
        *,
        second_speaker_needed: bool = False,
        primary_extracted_memory: dict | None = None,
        primary_disclosed_memory_ids: list[str] | None = None,
    ) -> None:
        self.second_speaker_needed = second_speaker_needed
        self.primary_extracted_memory = primary_extracted_memory
        self.primary_disclosed_memory_ids = primary_disclosed_memory_ids or []
        self.requests: list[SpeakerTurnRequest] = []

    async def create_speaker_turn(
        self, request: SpeakerTurnRequest
    ) -> SpeakerTurnResult:
        self.requests.append(request)
        if request.role == "PRIMARY":
            return SpeakerTurnResult(
                speaker_id=request.speaker.id,
                to="USER",
                emotion="concern",
                text="그 일이 계속 마음에 남아 있었구나.",
                needs_second_speaker=self.second_speaker_needed,
                second_speaker_reason=(
                    "DIFFERING_VIEWPOINT" if self.second_speaker_needed else "NONE"
                ),
                extracted_memory=self.primary_extracted_memory
                or {"has_memory": False, "content": "", "sensitivity": "PERSONAL"},
                disclosed_memory_ids=self.primary_disclosed_memory_ids,
            )
        return SpeakerTurnResult(
            speaker_id=request.speaker.id,
            to="USER",
            emotion="calm",
            text="나는 조금 다르게 생각해.",
        )


def test_create_talk_conversation() -> None:
    repository = FakeRepository()
    service = ConversationService(
        repository, FakeSceneDirector(), FakeMemoryRepository(memories_by_viewer={})
    )

    result = service.create_conversation(
        ConversationCreate(character_ids=["character_a", "character_b"])
    )

    assert result.status == "ACTIVE"
    assert result.character_ids == ["character_a", "character_b"]


def test_reject_unknown_character_before_database_write() -> None:
    repository = FakeRepository()
    service = ConversationService(
        repository, FakeSceneDirector(), FakeMemoryRepository(memories_by_viewer={})
    )

    with pytest.raises(InvalidResourceInputError):
        service.create_conversation(
            ConversationCreate(character_ids=["unknown_character"])
        )


def test_message_generates_single_turn_from_whoever_spoke_last() -> None:
    repository = FakeRepository()
    scene_director = FakeSceneDirector()
    memory_repository = FakeMemoryRepository(memories_by_viewer={})
    service = ConversationService(repository, scene_director, memory_repository)

    result = asyncio.run(
        service.create_message(
            repository.conversation_id,
            MessageCreate(content="오늘 회사에서 조금 힘들었어."),
        )
    )

    assert repository.saved_user_message is not None
    assert repository.saved_plan is not None
    assert len(repository.saved_plan.turns) == 1
    # character_b spoke last in recent_messages. Without an explicit name in
    # user_text, the user's next line is presumptively a reply to whoever
    # they were just talking to, so character_b continues -- forcing
    # alternation here would misroute direct replies/objections to the
    # other character (see the C_MULTI_004 eval finding).
    assert result.assistant_messages[0].speaker_id == "character_b"
    assert len(scene_director.requests) == 1
    assert scene_director.requests[0].role == "PRIMARY"
    assert scene_director.requests[0].speaker.id == "character_b"
    assert len(memory_repository.requested_viewers) == 1
    assert (
        memory_repository.requested_viewers[0]
        == repository.character_instance_ids["character_b"]
    )


def test_second_speaker_gets_an_independent_call_with_only_their_own_memory() -> None:
    repository = FakeRepository()
    scene_director = FakeSceneDirector(second_speaker_needed=True)
    character_a_id = repository.character_instance_ids["character_a"]
    character_b_id = repository.character_instance_ids["character_b"]
    memory_repository = FakeMemoryRepository(
        memories_by_viewer={
            character_a_id: [
                MemoryRecord(
                    id=uuid4(),
                    content="A만 아는 비공개 면접 고민",
                    memory_type="RELATIONSHIP",
                    sensitivity="PRIVATE",
                    owner_character_instance_id=character_a_id,
                )
            ],
            character_b_id: [
                MemoryRecord(
                    id=uuid4(),
                    content="B만 아는 비공개 반려동물 이야기",
                    memory_type="RELATIONSHIP",
                    sensitivity="PRIVATE",
                    owner_character_instance_id=character_b_id,
                )
            ],
        }
    )
    service = ConversationService(repository, scene_director, memory_repository)

    result = asyncio.run(
        service.create_message(
            repository.conversation_id,
            MessageCreate(content="오늘 회사에서 조금 힘들었어."),
        )
    )

    assert len(repository.saved_plan.turns) == 2
    # character_b spoke last, so it takes the primary turn (see
    # _order_speakers); character_a is the secondary speaker here.
    assert result.assistant_messages[0].speaker_id == "character_b"
    assert result.assistant_messages[1].speaker_id == "character_a"
    assert [request.role for request in scene_director.requests] == [
        "PRIMARY",
        "SECONDARY",
    ]
    # Each speaker's own memory lookup only, never the other speaker's.
    assert memory_repository.requested_viewers == [character_b_id, character_a_id]

    primary_request, secondary_request = scene_director.requests
    primary_contents = {item.content for item in primary_request.memory_context}
    secondary_contents = {item.content for item in secondary_request.memory_context}
    assert primary_contents == {"B만 아는 비공개 반려동물 이야기"}
    assert secondary_contents == {"A만 아는 비공개 면접 고민"}
    # A's private memory never crosses into B's request, and vice versa.
    assert "A만 아는 비공개 면접 고민" not in primary_contents
    assert "B만 아는 비공개 반려동물 이야기" not in secondary_contents
    # The secondary call only sees the already-spoken (public) primary turn,
    # folded into recent_messages, not a copy of A's private memory context.
    assert secondary_request.recent_messages[-1].content == (
        "그 일이 계속 마음에 남아 있었구나."
    )


def test_completed_conversation_rejects_new_message() -> None:
    repository = FakeRepository()
    repository.status = "COMPLETED"
    service = ConversationService(
        repository, FakeSceneDirector(), FakeMemoryRepository(memories_by_viewer={})
    )

    with pytest.raises(ResourceConflictError):
        asyncio.run(
            service.create_message(
                repository.conversation_id,
                MessageCreate(content="완료된 대화에 보낼 메시지"),
            )
        )


def test_extracted_memory_is_stored_with_shared_mode_acl() -> None:
    repository = FakeRepository()
    repository.memory_sharing_mode = "SHARED"
    scene_director = FakeSceneDirector(
        primary_extracted_memory={
            "has_memory": True,
            "content": "사용자는 다음 주 면접이 걱정된다고 말했다.",
            "sensitivity": "PRIVATE",
        }
    )
    memory_repository = FakeMemoryRepository(memories_by_viewer={})
    service = ConversationService(repository, scene_director, memory_repository)

    asyncio.run(
        service.create_message(
            repository.conversation_id,
            MessageCreate(content="오늘 회사에서 조금 힘들었어."),
        )
    )

    # character_b is the primary speaker here (see the whoever-spoke-last
    # test above), so it owns the extracted memory.
    assert len(memory_repository.created_memories) == 1
    created = memory_repository.created_memories[0]
    assert created["content"] == "사용자는 다음 주 면접이 걱정된다고 말했다."
    assert created["owner_character_instance_id"] == (
        repository.character_instance_ids["character_b"]
    )
    assert set(created["readable_by"]) == {
        repository.character_instance_ids["character_a"],
        repository.character_instance_ids["character_b"],
    }


def test_extracted_memory_stays_private_when_sharing_mode_is_none() -> None:
    repository = FakeRepository()
    repository.memory_sharing_mode = "NONE"
    scene_director = FakeSceneDirector(
        primary_extracted_memory={
            "has_memory": True,
            "content": "사용자는 다음 주 면접이 걱정된다고 말했다.",
            "sensitivity": "PRIVATE",
        }
    )
    memory_repository = FakeMemoryRepository(memories_by_viewer={})
    service = ConversationService(repository, scene_director, memory_repository)

    asyncio.run(
        service.create_message(
            repository.conversation_id,
            MessageCreate(content="오늘 회사에서 조금 힘들었어."),
        )
    )

    created = memory_repository.created_memories[0]
    assert created["readable_by"] == [
        repository.character_instance_ids["character_b"]
    ]


def test_disclosed_memory_surfaces_as_a_share_suggestion_without_changing_acl() -> None:
    repository = FakeRepository()
    character_b_id = repository.character_instance_ids["character_b"]
    disclosed_memory = MemoryRecord(
        id=uuid4(),
        content="B만 아는 비공개 반려동물 이야기",
        memory_type="RELATIONSHIP",
        sensitivity="PRIVATE",
        owner_character_instance_id=character_b_id,
    )
    memory_repository = FakeMemoryRepository(
        memories_by_viewer={character_b_id: [disclosed_memory]}
    )
    scene_director = FakeSceneDirector(
        primary_disclosed_memory_ids=[str(disclosed_memory.id)]
    )
    service = ConversationService(repository, scene_director, memory_repository)

    result = asyncio.run(
        service.create_message(
            repository.conversation_id,
            MessageCreate(content="오늘 회사에서 조금 힘들었어."),
        )
    )

    assert len(result.share_suggestions) == 1
    suggestion = result.share_suggestions[0]
    assert suggestion.memory_id == disclosed_memory.id
    assert suggestion.from_character_id == "character_b"
    assert suggestion.to_character_id == "character_a"
    # Speaking it aloud is not itself a grant -- no ACL call happened.
    assert memory_repository.created_memories == []
