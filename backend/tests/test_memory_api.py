from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_memory_service
from app.main import app
from app.schemas.memory import (
    MemoryAccessLogEntry,
    MemoryAccessLogResponse,
    MemoryCreate,
    MemoryListResponse,
    MemoryRead,
    MemoryShareGrant,
)


MEMORY_ID = uuid4()
MEMORY = MemoryRead(
    id=MEMORY_ID,
    content="사용자는 다음 주 면접이 걱정된다고 말했다.",
    memory_type="RELATIONSHIP",
    sensitivity="PRIVATE",
    owner_character_id="character_a",
)


class FakeMemoryService:
    def __init__(self) -> None:
        self.deleted: UUID | None = None
        self.shared: tuple[UUID, MemoryShareGrant] | None = None
        self.revoked: tuple[UUID, str] | None = None

    def list_memories(self, viewer_character_id: str) -> MemoryListResponse:
        assert viewer_character_id == "character_a"
        return MemoryListResponse(items=[MEMORY])

    def create_memory(self, request: MemoryCreate) -> MemoryRead:
        return MEMORY.model_copy(update={"content": request.content})

    def delete_memory(self, memory_id: UUID) -> None:
        self.deleted = memory_id

    def share_memory(self, memory_id: UUID, request: MemoryShareGrant) -> None:
        self.shared = (memory_id, request)

    def revoke_share(self, memory_id: UUID, character_id: str) -> None:
        self.revoked = (memory_id, character_id)

    def list_access_log(
        self, *, memory_id: UUID | None = None, conversation_id: UUID | None = None
    ) -> MemoryAccessLogResponse:
        del conversation_id
        return MemoryAccessLogResponse(
            items=[
                MemoryAccessLogEntry(
                    memory_id=memory_id or MEMORY_ID,
                    requesting_character_id="character_a",
                    action="RETRIEVE",
                    decision="ALLOW",
                    reason_code="OWNER",
                    created_at="2026-08-18T00:00:00+00:00",
                )
            ]
        )


client = TestClient(app)
service = FakeMemoryService()


def setup_function() -> None:
    global service
    service = FakeMemoryService()
    app.dependency_overrides[get_memory_service] = lambda: service


def teardown_function() -> None:
    app.dependency_overrides = {}


def test_list_memories_requires_viewer_character_id() -> None:
    response = client.get("/api/v1/memories", params={"viewer_character_id": "character_a"})

    assert response.status_code == 200
    assert response.json()["items"][0]["owner_character_id"] == "character_a"


def test_create_memory_returns_created_status() -> None:
    response = client.post(
        "/api/v1/memories",
        json={
            "content": "사용자는 커피를 좋아한다.",
            "memory_type": "USER_GLOBAL",
            "readable_by_character_ids": ["character_a", "character_b"],
        },
    )

    assert response.status_code == 201
    assert response.json()["content"] == "사용자는 커피를 좋아한다."


def test_delete_memory_calls_service() -> None:
    response = client.delete(f"/api/v1/memories/{MEMORY_ID}")

    assert response.status_code == 204
    assert service.deleted == MEMORY_ID


def test_share_memory_calls_service_with_grant() -> None:
    response = client.post(
        f"/api/v1/memories/{MEMORY_ID}/share",
        json={"grant_to_character_id": "character_b", "can_disclose_to": True},
    )

    assert response.status_code == 204
    assert service.shared is not None
    memory_id, grant = service.shared
    assert memory_id == MEMORY_ID
    assert grant.grant_to_character_id == "character_b"


def test_revoke_memory_share_calls_service() -> None:
    response = client.delete(f"/api/v1/memories/{MEMORY_ID}/share/character_b")

    assert response.status_code == 204
    assert service.revoked == (MEMORY_ID, "character_b")


def test_list_access_log_returns_entries() -> None:
    response = client.get("/api/v1/memories/access-log")

    assert response.status_code == 200
    entry = response.json()["items"][0]
    assert entry["decision"] == "ALLOW"
    assert entry["reason_code"] == "OWNER"
