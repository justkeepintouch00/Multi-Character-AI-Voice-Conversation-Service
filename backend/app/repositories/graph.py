from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import MemoryACL, MemoryAccessLog, MemoryGraphEdge, MemoryItem
from app.memory.policy import MemoryPolicyVersion


@dataclass(frozen=True, slots=True)
class GraphFact:
    """An ACL-authorized fact rendered from one memory graph edge."""

    memory_id: UUID
    source_entity: str
    relation: str
    target_entity: str
    summary: str | None
    sensitivity: str

    @property
    def text(self) -> str:
        detail = f" ({self.summary})" if self.summary else ""
        return f"{self.source_entity} —[{self.relation}]→ {self.target_entity}{detail}"


class GraphMemoryRepository(Protocol):
    def create_edge(
        self,
        *,
        user_id: UUID,
        memory_id: UUID,
        source_entity: str,
        relation: str,
        target_entity: str,
        summary: str | None = None,
    ) -> None: ...

    def retrieve_related(
        self,
        *,
        user_id: UUID,
        viewer_character_instance_id: UUID,
        query_terms: list[str],
        limit: int = 5,
        conversation_id: UUID | None = None,
    ) -> list[GraphFact]: ...


class SQLAlchemyGraphMemoryRepository:
    """Partial GraphRAG store.

    Graph edges never bypass memory ACLs: every traversal joins the edge to its
    source memory item and then to the requesting character's ``memory_acl``.
    This keeps graph retrieval subject to the same privacy boundary as ordinary
    memory retrieval.
    """

    def __init__(self, session: Session, policy_version: str = "v1") -> None:
        self.session = session
        try:
            self.policy_version = MemoryPolicyVersion(policy_version).value
        except ValueError as exc:
            raise ValueError("policy_version must be v1 or v2") from exc

    def create_edge(
        self,
        *,
        user_id: UUID,
        memory_id: UUID,
        source_entity: str,
        relation: str,
        target_entity: str,
        summary: str | None = None,
    ) -> None:
        edge = MemoryGraphEdge(
            created_at=datetime.now(timezone.utc),
            user_id=user_id,
            memory_id=memory_id,
            source_entity=source_entity.strip(),
            relation=relation.strip(),
            target_entity=target_entity.strip(),
            summary=summary.strip() if summary else None,
            policy_version=self.policy_version,
        )
        self.session.add(edge)
        self.session.commit()

    def retrieve_related(
        self,
        *,
        user_id: UUID,
        viewer_character_instance_id: UUID,
        query_terms: list[str],
        limit: int = 5,
        conversation_id: UUID | None = None,
    ) -> list[GraphFact]:
        terms = [term.strip() for term in query_terms if len(term.strip()) >= 2]
        if not terms:
            return []
        now = datetime.now(timezone.utc)
        matches = []
        for term in terms:
            pattern = f"%{term}%"
            matches.extend(
                [
                    MemoryGraphEdge.source_entity.ilike(pattern),
                    MemoryGraphEdge.relation.ilike(pattern),
                    MemoryGraphEdge.target_entity.ilike(pattern),
                    MemoryGraphEdge.summary.ilike(pattern),
                ]
            )
        rows = list(
            self.session.execute(
                select(MemoryGraphEdge, MemoryItem.sensitivity)
                .join(MemoryItem, MemoryItem.id == MemoryGraphEdge.memory_id)
                .join(
                    MemoryACL,
                    (MemoryACL.memory_id == MemoryItem.id)
                    & (MemoryACL.subject_type == "CHARACTER_INSTANCE")
                    & (MemoryACL.subject_id == viewer_character_instance_id),
                )
                .where(
                    MemoryGraphEdge.user_id == user_id,
                    MemoryGraphEdge.policy_version == self.policy_version,
                    MemoryGraphEdge.status == "CONFIRMED",
                    or_(MemoryGraphEdge.valid_from.is_(None), MemoryGraphEdge.valid_from <= now),
                    # Keep graph facts within the current conversation;
                    # ACL alone does not prevent cross-conversation leakage.
                    or_(
                        conversation_id is None,
                        MemoryItem.source_conversation_id == conversation_id,
                        MemoryItem.source_conversation_id.is_(None),
                    ),
                    MemoryItem.policy_version == self.policy_version,
                    MemoryItem.status == "CONFIRMED",
                    MemoryItem.deleted_at.is_(None),
                    or_(MemoryItem.expires_at.is_(None), MemoryItem.expires_at > now),
                    or_(MemoryGraphEdge.valid_to.is_(None), MemoryGraphEdge.valid_to > now),
                    MemoryACL.can_read.is_(True),
                    or_(*matches),
                )
                .order_by(MemoryGraphEdge.created_at.desc())
                .limit(limit)
            ).all()
        )
        facts = [
            GraphFact(
                memory_id=edge.memory_id,
                source_entity=edge.source_entity,
                relation=edge.relation,
                target_entity=edge.target_entity,
                summary=edge.summary,
                sensitivity=sensitivity,
            )
            for edge, sensitivity in rows
        ]
        for fact in facts:
            self.session.add(
                MemoryAccessLog(
                    conversation_id=conversation_id,
                    memory_id=fact.memory_id,
                    requesting_character_instance_id=viewer_character_instance_id,
                    action="RETRIEVE",
                    decision="ALLOW",
                    reason_code="ACL",
                )
            )
        if facts:
            self.session.commit()
        return facts

