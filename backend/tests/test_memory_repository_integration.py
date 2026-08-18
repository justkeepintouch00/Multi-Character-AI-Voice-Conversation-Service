from __future__ import annotations

import os

import pytest
from sqlalchemy.orm import Session

from app.db.session import engine
from app.repositories.characters import SQLAlchemyCharacterRepository
from app.repositories.memory import SQLAlchemyMemoryRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1",
    reason="Set RUN_POSTGRES_TESTS=1 to run the rollback-only PostgreSQL test",
)


def test_private_memory_is_isolated_between_characters() -> None:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    session.commit = session.flush  # type: ignore[method-assign]

    try:
        characters = SQLAlchemyCharacterRepository(
            session,
            development_user_external_id="memory-repository-integration-test-user",
            development_user_display_name="Memory 통합 테스트 사용자",
        )
        context = characters.ensure_development_context()
        user_id = context.user_id
        character_a_id = context.character_instance_ids["character_a"]
        character_b_id = context.character_instance_ids["character_b"]

        memory = SQLAlchemyMemoryRepository(session)

        # A's private memory: only A may read it until it is explicitly shared.
        private_a = memory.create_memory(
            user_id=user_id,
            content="사용자는 다음 주 면접이 걱정된다고 말했다.",
            memory_type="RELATIONSHIP",
            owner_character_instance_id=character_a_id,
            sensitivity="PRIVATE",
            granted_by_user_id=user_id,
        )

        # A shared fact: both A and B are granted read access at creation time.
        shared_ab = memory.create_memory(
            user_id=user_id,
            content="사용자는 단 음식을 좋아한다.",
            memory_type="USER_GLOBAL",
            owner_character_instance_id=None,
            sensitivity="PERSONAL",
            granted_by_user_id=user_id,
            readable_by=[character_a_id, character_b_id],
        )

        a_view = memory.retrieve(
            user_id=user_id, viewer_character_instance_id=character_a_id
        )
        b_view = memory.retrieve(
            user_id=user_id, viewer_character_instance_id=character_b_id
        )

        assert {record.id for record in a_view} == {private_a.id, shared_ab.id}
        assert {record.id for record in b_view} == {shared_ab.id}

        # Single-item checks back the same result and produce an audit row.
        a_on_private = memory.check_access(
            memory_id=private_a.id, requesting_character_instance_id=character_a_id
        )
        b_on_private = memory.check_access(
            memory_id=private_a.id, requesting_character_instance_id=character_b_id
        )
        assert a_on_private.decision == "ALLOW"
        assert a_on_private.reason_code == "OWNER"
        assert b_on_private.decision == "DENY"
        assert b_on_private.reason_code == "NO_PERMISSION"

        # Sharing PRIVATE_A -> SHARED_AB flips B's access without touching A's.
        memory.grant_read_access(
            memory_id=private_a.id,
            subject_character_instance_id=character_b_id,
            granted_by_user_id=user_id,
        )
        b_after_share = memory.retrieve(
            user_id=user_id, viewer_character_instance_id=character_b_id
        )
        assert private_a.id in {record.id for record in b_after_share}

        # Deleting removes it from both viewers regardless of prior grants.
        memory.delete_memory(private_a.id)
        a_after_delete = memory.retrieve(
            user_id=user_id, viewer_character_instance_id=character_a_id
        )
        b_after_delete = memory.retrieve(
            user_id=user_id, viewer_character_instance_id=character_b_id
        )
        assert private_a.id not in {record.id for record in a_after_delete}
        assert private_a.id not in {record.id for record in b_after_delete}
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()
