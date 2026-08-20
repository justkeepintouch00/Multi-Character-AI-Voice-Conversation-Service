from __future__ import annotations

from uuid import UUID

from app.repositories.characters import DevelopmentContext, SQLAlchemyCharacterRepository
from app.repositories.memory import MemoryRecord, MemoryRepository
from app.schemas.memory import (
    MemoryAccessLogEntry,
    MemoryAccessLogResponse,
    MemoryCreate,
    MemoryListResponse,
    MemoryRead,
    MemoryShareGrant,
)
from app.services.errors import InvalidResourceInputError, ResourceNotFoundError

_OWNED_MEMORY_TYPES = {"RELATIONSHIP", "CHARACTER_INTERNAL"}
_UNOWNED_MEMORY_TYPES = {"USER_GLOBAL", "GROUP"}


class MemoryService:
    def __init__(
        self,
        character_repository: SQLAlchemyCharacterRepository,
        memory_repository: MemoryRepository,
    ) -> None:
        self.character_repository = character_repository
        self.memory_repository = memory_repository

    def list_memories(self, viewer_character_id: str) -> MemoryListResponse:
        context = self.character_repository.ensure_development_context()
        instance_id = self._instance_id(context, viewer_character_id)
        records = self.memory_repository.retrieve(
            user_id=context.user_id,
            viewer_character_instance_id=instance_id,
            limit=200,
        )
        reverse_ids = self._reverse_ids(context)
        return MemoryListResponse(
            items=[self._to_read(record, reverse_ids) for record in records]
        )

    def create_memory(self, request: MemoryCreate) -> MemoryRead:
        if request.memory_type in _OWNED_MEMORY_TYPES and request.owner_character_id is None:
            raise InvalidResourceInputError(
                "이 memory_type은 owner_character_id가 필요합니다."
            )
        if (
            request.memory_type in _UNOWNED_MEMORY_TYPES
            and request.owner_character_id is not None
        ):
            raise InvalidResourceInputError(
                "이 memory_type은 owner_character_id를 지정할 수 없습니다."
            )

        context = self.character_repository.ensure_development_context()
        owner_instance_id = (
            self._instance_id(context, request.owner_character_id)
            if request.owner_character_id is not None
            else None
        )
        readable_by = [
            self._instance_id(context, character_id)
            for character_id in request.readable_by_character_ids
        ]
        record = self.memory_repository.create_memory(
            user_id=context.user_id,
            content=request.content,
            memory_type=request.memory_type,
            owner_character_instance_id=owner_instance_id,
            sensitivity=request.sensitivity,
            granted_by_user_id=context.user_id,
            readable_by=readable_by,
            can_disclose_to=request.can_disclose_to,
        )
        return self._to_read(record, self._reverse_ids(context))

    def delete_memory(self, memory_id: UUID) -> None:
        self.memory_repository.delete_memory(memory_id)

    def share_memory(self, memory_id: UUID, request: MemoryShareGrant) -> None:
        context = self.character_repository.ensure_development_context()
        subject_instance_id = self._instance_id(
            context, request.grant_to_character_id
        )
        self.memory_repository.grant_read_access(
            memory_id=memory_id,
            subject_character_instance_id=subject_instance_id,
            granted_by_user_id=context.user_id,
            can_disclose_to=request.can_disclose_to,
        )

    def revoke_share(self, memory_id: UUID, character_id: str) -> None:
        context = self.character_repository.ensure_development_context()
        subject_instance_id = self._instance_id(context, character_id)
        self.memory_repository.revoke_read_access(
            memory_id=memory_id, subject_character_instance_id=subject_instance_id
        )

    def list_access_log(
        self,
        *,
        memory_id: UUID | None = None,
        conversation_id: UUID | None = None,
    ) -> MemoryAccessLogResponse:
        context = self.character_repository.ensure_development_context()
        reverse_ids = self._reverse_ids(context)
        entries = self.memory_repository.list_access_logs(
            memory_id=memory_id, conversation_id=conversation_id
        )
        return MemoryAccessLogResponse(
            items=[
                MemoryAccessLogEntry(
                    memory_id=entry.memory_id,
                    requesting_character_id=reverse_ids.get(
                        entry.requesting_character_instance_id,
                        str(entry.requesting_character_instance_id),
                    ),
                    action=entry.action,
                    decision=entry.decision,
                    reason_code=entry.reason_code,
                    created_at=entry.created_at.isoformat(),
                )
                for entry in entries
            ]
        )

    @staticmethod
    def _instance_id(context: DevelopmentContext, character_id: str) -> UUID:
        instance_id = context.character_instance_ids.get(character_id)
        if instance_id is None:
            raise ResourceNotFoundError("캐릭터를 찾을 수 없습니다.")
        return instance_id

    @staticmethod
    def _reverse_ids(context: DevelopmentContext) -> dict[UUID, str]:
        return {
            instance_id: public_id
            for public_id, instance_id in context.character_instance_ids.items()
        }

    @staticmethod
    def _to_read(record: MemoryRecord, reverse_ids: dict[UUID, str]) -> MemoryRead:
        return MemoryRead(
            id=record.id,
            content=record.content,
            memory_type=record.memory_type,
            sensitivity=record.sensitivity,
            owner_character_id=(
                reverse_ids.get(record.owner_character_instance_id)
                if record.owner_character_instance_id is not None
                else None
            ),
        )
