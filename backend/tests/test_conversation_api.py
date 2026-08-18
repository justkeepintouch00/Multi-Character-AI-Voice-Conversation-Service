from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_conversation_service
from app.main import app
from app.schemas.conversation import ConversationCreate, ConversationRead
from app.schemas.message import (
    MessageCreate,
    MessageExchangeResponse,
    MessageListResponse,
    MessageRead,
)
from app.schemas.scene_plan import ScenePlan


NOW = datetime.now(timezone.utc)
CONVERSATION_ID = uuid4()
client = TestClient(app)


class FakeConversationService:
    def create_conversation(self, request: ConversationCreate) -> ConversationRead:
        return self._conversation(request.character_ids)

    def get_conversation(self, conversation_id: UUID) -> ConversationRead:
        assert conversation_id == CONVERSATION_ID
        return self._conversation(["character_a", "character_b"])

    def complete_conversation(self, conversation_id: UUID) -> ConversationRead:
        result = self.get_conversation(conversation_id)
        return result.model_copy(update={"status": "COMPLETED", "closed_at": NOW})

    async def create_message(
        self, conversation_id: UUID, request: MessageCreate
    ) -> MessageExchangeResponse:
        assert conversation_id == CONVERSATION_ID
        user_message = self._message("USER", None, request.content, request.input_mode)
        plan = ScenePlan.model_validate(
            {
                "scene_action": "CHARACTER_SEQUENCE",
                "turns": [
                    {
                        "speaker_id": "character_a",
                        "to": "USER",
                        "emotion": "calm",
                        "text": "천천히 이야기해도 괜찮아.",
                    }
                ],
                "return_turn_to": "USER",
                "max_internal_turns": 1,
            }
        )
        return MessageExchangeResponse(
            user_message=user_message,
            scene_plan=plan,
            assistant_messages=[
                self._message(
                    "CHARACTER",
                    "character_a",
                    plan.turns[0].text,
                    "SYSTEM",
                )
            ],
        )

    def list_messages(
        self, conversation_id: UUID, limit: int
    ) -> MessageListResponse:
        assert conversation_id == CONVERSATION_ID
        assert limit == 50
        return MessageListResponse(items=[])

    @staticmethod
    def _conversation(character_ids: list[str]) -> ConversationRead:
        return ConversationRead(
            id=CONVERSATION_ID,
            mode="TALK",
            status="ACTIVE",
            character_ids=character_ids,
            memory_sharing_mode="NONE",
            created_at=NOW,
            updated_at=NOW,
            closed_at=None,
        )

    @staticmethod
    def _message(
        speaker_type: str,
        speaker_id: str | None,
        content: str,
        input_mode: str,
    ) -> MessageRead:
        return MessageRead(
            id=uuid4(),
            speaker_type=speaker_type,
            speaker_id=speaker_id,
            content=content,
            input_mode=input_mode,
            finalized=True,
            interrupted=False,
            created_at=NOW,
        )


@pytest.fixture(autouse=True)
def override_service():
    app.dependency_overrides[get_conversation_service] = FakeConversationService
    yield
    app.dependency_overrides = {}


def test_create_and_get_conversation_routes() -> None:
    created = client.post(
        "/api/v1/conversations",
        json={"mode": "TALK", "character_ids": ["character_a", "character_b"]},
    )
    fetched = client.get(f"/api/v1/conversations/{CONVERSATION_ID}")

    assert created.status_code == 201
    assert fetched.status_code == 200
    assert fetched.json()["id"] == str(CONVERSATION_ID)


def test_create_message_route_returns_persistable_exchange_shape() -> None:
    response = client.post(
        f"/api/v1/conversations/{CONVERSATION_ID}/messages",
        json={"content": "오늘 조금 힘들었어.", "input_mode": "TEXT"},
    )

    assert response.status_code == 200
    assert response.json()["user_message"]["speaker_type"] == "USER"
    assert response.json()["assistant_messages"][0]["speaker_id"] == "character_a"


def test_message_list_limit_is_validated() -> None:
    response = client.get(
        f"/api/v1/conversations/{CONVERSATION_ID}/messages?limit=101"
    )

    assert response.status_code == 422
