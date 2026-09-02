from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import MemoryACL, MemoryAccessLog, MemoryItem
from app.memory.policy import MemoryPolicyVersion


ReasonCode = Literal["OWNER", "ACL", "NO_PERMISSION", "DELETED", "EXPIRED"]
Decision = Literal["ALLOW", "DENY"]


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    id: UUID
    content: str
    memory_type: str
    sensitivity: str
    owner_character_instance_id: UUID | None
    policy_version: str = "v1"
    status: str = "CONFIRMED"
    confidence: float = 1.0

@dataclass(frozen=True, slots=True)
class AccessDecision:
    memory_id: UUID
    requesting_character_instance_id: UUID
    decision: Decision
    reason_code: ReasonCode


@dataclass(frozen=True, slots=True)
class AccessLogEntry:
    memory_id: UUID
    requesting_character_instance_id: UUID
    action: str
    decision: Decision
    reason_code: ReasonCode
    created_at: datetime


class MemoryRepository(Protocol):
    def retrieve(
        self,
        *,
        user_id: UUID,
        viewer_character_instance_id: UUID,
        limit: int = 8,
        conversation_id: UUID | None = None,
        scene_plan_id: UUID | None = None,
    ) -> list[MemoryRecord]: ...

    def check_access(
        self,
        *,
        memory_id: UUID,
        requesting_character_instance_id: UUID,
        conversation_id: UUID | None = None,
        scene_plan_id: UUID | None = None,
    ) -> AccessDecision: ...

    def create_memory(
        self,
        *,
        user_id: UUID,
        content: str,
        memory_type: str,
        owner_character_instance_id: UUID | None,
        sensitivity: str,
        granted_by_user_id: UUID,
        readable_by: list[UUID] | None = None,
        can_disclose_to: bool = False,
        source_conversation_id: UUID | None = None,
    ) -> MemoryRecord: ...

    def delete_memory(self, memory_id: UUID) -> None: ...

    def grant_read_access(
        self,
        *,
        memory_id: UUID,
        subject_character_instance_id: UUID,
        granted_by_user_id: UUID,
        can_disclose_to: bool = True,
    ) -> None: ...

    def revoke_read_access(
        self, *, memory_id: UUID, subject_character_instance_id: UUID
    ) -> None: ...

    def list_access_logs(
        self,
        *,
        memory_id: UUID | None = None,
        conversation_id: UUID | None = None,
        limit: int = 50,
    ) -> list[AccessLogEntry]: ...


class SQLAlchemyMemoryRepository:
    """ACL-first memory access.

    Every read path — bulk retrieval for prompt-building and single-item
    checks for the audit screen — goes through ``memory_acl``. There is no
    code path that returns a memory item without an explicit ``can_read``
    grant for the requesting character, including the owner.
    """

    def __init__(self, session: Session, policy_version: str = "v1") -> None:
        self.session = session
        try:
            self.policy_version = MemoryPolicyVersion(policy_version).value
        except ValueError as exc:
            raise ValueError("policy_version must be v1 or v2") from exc

    def retrieve(
        self,
        *,
        user_id: UUID,
        viewer_character_instance_id: UUID,
        limit: int = 8,
        conversation_id: UUID | None = None,
        scene_plan_id: UUID | None = None,
    ) -> list[MemoryRecord]:
        now = datetime.now(timezone.utc)
        items = list(
            self.session.execute(
                select(MemoryItem)
                .join(
                    MemoryACL,
                    (MemoryACL.memory_id == MemoryItem.id)
                    & (MemoryACL.subject_type == "CHARACTER_INSTANCE")
                    & (MemoryACL.subject_id == viewer_character_instance_id),
                )
                .where(
                    MemoryItem.user_id == user_id,
                    MemoryItem.policy_version == self.policy_version,
                    MemoryItem.status == "CONFIRMED",
                    or_(MemoryItem.valid_from.is_(None), MemoryItem.valid_from <= now),
                    # Restrict retrieval to this conversation plus explicit
                    # character seed memories (source_conversation_id IS NULL).
                    # ACL alone is insufficient because it would expose
                    # memories from unrelated past conversations.
                    or_(
                        conversation_id is None,
                        MemoryItem.source_conversation_id == conversation_id,
                        MemoryItem.source_conversation_id.is_(None),
                    ),
                    MemoryItem.deleted_at.is_(None),
                    or_(
                        MemoryItem.expires_at.is_(None),
                        MemoryItem.expires_at > now,
                    ),
                    or_(MemoryItem.valid_to.is_(None), MemoryItem.valid_to > now),
                    MemoryACL.can_read.is_(True),
                )
                .order_by(MemoryItem.created_at.desc())
                .limit(limit)
            ).scalars()
        )
        records = [self._to_record(item) for item in items]
        for record in records:
            reason_code: ReasonCode = (
                "OWNER"
                if record.owner_character_instance_id == viewer_character_instance_id
                else "ACL"
            )
            self._log(
                memory_id=record.id,
                requesting_character_instance_id=viewer_character_instance_id,
                action="RETRIEVE",
                decision="ALLOW",
                reason_code=reason_code,
                conversation_id=conversation_id,
                scene_plan_id=scene_plan_id,
            )
        return records

    def check_access(
        self,
        *,
        memory_id: UUID,
        requesting_character_instance_id: UUID,
        conversation_id: UUID | None = None,
        scene_plan_id: UUID | None = None,
    ) -> AccessDecision:
        item = self.session.get(MemoryItem, memory_id)
        decision, reason_code = self._evaluate(
            item, requesting_character_instance_id
        )
        self._log(
            memory_id=memory_id,
            requesting_character_instance_id=requesting_character_instance_id,
            action="RETRIEVE",
            decision=decision,
            reason_code=reason_code,
            conversation_id=conversation_id,
            scene_plan_id=scene_plan_id,
        )
        return AccessDecision(
            memory_id=memory_id,
            requesting_character_instance_id=requesting_character_instance_id,
            decision=decision,
            reason_code=reason_code,
        )

    def create_memory(
        self,
        *,
        user_id: UUID,
        content: str,
        memory_type: str,
        owner_character_instance_id: UUID | None,
        sensitivity: str,
        granted_by_user_id: UUID,
        readable_by: list[UUID] | None = None,
        can_disclose_to: bool = False,
        source_conversation_id: UUID | None = None,
    ) -> MemoryRecord:
        item = MemoryItem(
            user_id=user_id,
            memory_type=memory_type,
            owner_character_instance_id=owner_character_instance_id,
            content=content,
            sensitivity=sensitivity,
            source_conversation_id=source_conversation_id,
            policy_version=self.policy_version,
        )
        self.session.add(item)
        self.session.flush()

        subjects = set(readable_by or [])
        if owner_character_instance_id is not None:
            subjects.add(owner_character_instance_id)
        for subject_id in subjects:
            self.session.add(
                MemoryACL(
                    memory_id=item.id,
                    subject_type="CHARACTER_INSTANCE",
                    subject_id=subject_id,
                    can_know=True,
                    can_read=True,
                    can_disclose_to=can_disclose_to,
                    granted_by_user_id=granted_by_user_id,
                )
            )
        self.session.commit()
        return self._to_record(item)

    def delete_memory(self, memory_id: UUID) -> None:
        item = self.session.get(MemoryItem, memory_id)
        if item is not None and item.deleted_at is None:
            item.deleted_at = datetime.now(timezone.utc)
            self.session.commit()

    def grant_read_access(
        self,
        *,
        memory_id: UUID,
        subject_character_instance_id: UUID,
        granted_by_user_id: UUID,
        can_disclose_to: bool = True,
    ) -> None:
        acl = self.session.get(
            MemoryACL,
            {
                "memory_id": memory_id,
                "subject_type": "CHARACTER_INSTANCE",
                "subject_id": subject_character_instance_id,
            },
        )
        if acl is None:
            self.session.add(
                MemoryACL(
                    memory_id=memory_id,
                    subject_type="CHARACTER_INSTANCE",
                    subject_id=subject_character_instance_id,
                    can_know=True,
                    can_read=True,
                    can_disclose_to=can_disclose_to,
                    granted_by_user_id=granted_by_user_id,
                )
            )
        else:
            acl.can_know = True
            acl.can_read = True
            acl.can_disclose_to = can_disclose_to
        self.session.commit()

    def revoke_read_access(
        self, *, memory_id: UUID, subject_character_instance_id: UUID
    ) -> None:
        acl = self.session.get(
            MemoryACL,
            {
                "memory_id": memory_id,
                "subject_type": "CHARACTER_INSTANCE",
                "subject_id": subject_character_instance_id,
            },
        )
        if acl is not None and acl.can_read:
            acl.can_read = False
            self.session.commit()

    def list_access_logs(
        self,
        *,
        memory_id: UUID | None = None,
        conversation_id: UUID | None = None,
        limit: int = 50,
    ) -> list[AccessLogEntry]:
        query = (
            select(MemoryAccessLog)
            .order_by(MemoryAccessLog.created_at.desc())
            .limit(limit)
        )
        if memory_id is not None:
            query = query.where(MemoryAccessLog.memory_id == memory_id)
        if conversation_id is not None:
            query = query.where(MemoryAccessLog.conversation_id == conversation_id)
        rows = self.session.execute(query).scalars().all()
        return [
            AccessLogEntry(
                memory_id=row.memory_id,
                requesting_character_instance_id=row.requesting_character_instance_id,
                action=row.action,
                decision=row.decision,
                reason_code=row.reason_code,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def _evaluate(
        self,
        item: MemoryItem | None,
        requesting_character_instance_id: UUID,
    ) -> tuple[Decision, ReasonCode]:
        if item is None:
            return "DENY", "NO_PERMISSION"
        if item.deleted_at is not None:
            return "DENY", "DELETED"
        if item.expires_at is not None and item.expires_at <= datetime.now(
            timezone.utc
        ):
            return "DENY", "EXPIRED"
        acl = self.session.get(
            MemoryACL,
            {
                "memory_id": item.id,
                "subject_type": "CHARACTER_INSTANCE",
                "subject_id": requesting_character_instance_id,
            },
        )
        if acl is None:
            return "DENY", "NO_PERMISSION"
        if not acl.can_read:
            return "DENY", "ACL"
        if item.owner_character_instance_id == requesting_character_instance_id:
            return "ALLOW", "OWNER"
        return "ALLOW", "ACL"

    def _log(
        self,
        *,
        memory_id: UUID,
        requesting_character_instance_id: UUID,
        action: str,
        decision: Decision,
        reason_code: ReasonCode,
        conversation_id: UUID | None,
        scene_plan_id: UUID | None,
    ) -> None:
        self.session.add(
            MemoryAccessLog(
                conversation_id=conversation_id,
                memory_id=memory_id,
                requesting_character_instance_id=requesting_character_instance_id,
                action=action,
                decision=decision,
                reason_code=reason_code,
                scene_plan_id=scene_plan_id,
            )
        )
        self.session.commit()

    @staticmethod
    def _to_record(item: MemoryItem) -> MemoryRecord:
        return MemoryRecord(
            id=item.id,
            content=item.content,
            memory_type=item.memory_type,
            sensitivity=item.sensitivity,
            owner_character_instance_id=item.owner_character_instance_id,
            policy_version=item.policy_version,
            status=item.status,
            confidence=float(item.confidence),
        )
