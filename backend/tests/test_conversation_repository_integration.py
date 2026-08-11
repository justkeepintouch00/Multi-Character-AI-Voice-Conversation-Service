from __future__ import annotations

import os

import pytest
from sqlalchemy.orm import Session

from app.db.session import engine
from app.repositories.conversations import SQLAlchemyConversationRepository
from app.schemas.scene_plan import ScenePlan


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1",
    reason="Set RUN_POSTGRES_TESTS=1 to run the rollback-only PostgreSQL test",
)


def test_conversation_repository_round_trip_rolls_back() -> None:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    # Repository transaction boundaries are exercised as flushes while the outer
    # test transaction guarantees that no test records remain in PostgreSQL.
    session.commit = session.flush  # type: ignore[method-assign]

    try:
        repository = SQLAlchemyConversationRepository(
            session,
            development_user_external_id="repository-integration-test-user",
            development_user_display_name="Repository 통합 테스트 사용자",
        )
        context = repository.ensure_development_context()
        conversation = repository.create_conversation(
            context, "TALK", ["character_a", "character_b"]
        )
        user_message = repository.add_user_message(
            user_id=context.user_id,
            conversation_id=conversation.id,
            content="통합 테스트 메시지",
            input_mode="TEXT",
        )
        plan = ScenePlan.model_validate(
            {
                "scene_action": "CHARACTER_SEQUENCE",
                "turns": [
                    {
                        "speaker_id": "character_a",
                        "to": "USER",
                        "emotion": "calm",
                        "text": "통합 테스트 응답",
                    }
                ],
                "return_turn_to": "USER",
                "max_internal_turns": 1,
            }
        )
        assistant_messages = repository.save_scene_result(
            context=context,
            conversation_id=conversation.id,
            triggering_message_id=user_message.id,
            plan=plan,
        )

        stored_messages = repository.list_messages(conversation.id, 50)
        assert conversation.character_ids == ["character_a", "character_b"]
        assert assistant_messages[0].speaker_id == "character_a"
        assert [message.content for message in stored_messages] == [
            "통합 테스트 메시지",
            "통합 테스트 응답",
        ]
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()
