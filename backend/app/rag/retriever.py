from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda

from app.repositories.graph import GraphFact, GraphMemoryRepository
from app.repositories.memory import MemoryRecord, MemoryRepository


_RELATION_INTENT = re.compile(r"관계|사이|누구|누가|왜|이유|전|후|이후|기억|다시")
_TERM_PATTERN = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_STOPWORDS = frozenset({"그래서", "그리고", "오늘", "제가", "우리", "너무", "이것", "저것", "대한", "있는", "없는", "그런", "이런", "사용자"})


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    user_id: UUID
    viewer_character_instance_id: UUID
    conversation_id: UUID
    user_text: str


@dataclass(frozen=True, slots=True)
class RetrievalBundle:
    memory_records: list[MemoryRecord]
    graph_facts: list[GraphFact]
    documents: list[Document]


class LangChainMemoryGraphRetriever:
    """LangChain runnable over the existing ACL memory repository.

    The standard memory result is always retrieved first. Graph traversal is
    additive and conditional, so it cannot expand a character's permissions.
    ``Document`` objects make this retrieval boundary reusable by future
    LangChain chains without coupling the provider implementation to LangChain.
    """

    def __init__(
        self,
        memory_repository: MemoryRepository,
        graph_repository: GraphMemoryRepository | None = None,
    ) -> None:
        self.memory_repository = memory_repository
        self.graph_repository = graph_repository
        self.runnable = RunnableLambda(self._retrieve)

    def invoke(self, request: RetrievalRequest) -> RetrievalBundle:
        # The SQLAlchemy session is request-scoped and synchronous. Invoking
        # synchronously preserves its thread affinity inside FastAPI handlers.
        return self.runnable.invoke(request)

    def _retrieve(self, request: RetrievalRequest) -> RetrievalBundle:
        memory_records = self.memory_repository.retrieve(
            user_id=request.user_id,
            viewer_character_instance_id=request.viewer_character_instance_id,
            conversation_id=request.conversation_id,
        )
        graph_facts: list[GraphFact] = []
        if self.graph_repository is not None and _RELATION_INTENT.search(request.user_text):
            graph_facts = self.graph_repository.retrieve_related(
                user_id=request.user_id,
                viewer_character_instance_id=request.viewer_character_instance_id,
                query_terms=self._query_terms(request.user_text),
                conversation_id=request.conversation_id,
            )
        documents = [
            Document(
                page_content=record.content,
                metadata={
                    "memory_id": str(record.id),
                    "memory_type": record.memory_type,
                    "sensitivity": record.sensitivity,
                    "source": "acl_memory",
                },
            )
            for record in memory_records
        ]
        documents.extend(
            Document(
                page_content=fact.text,
                metadata={
                    "memory_id": str(fact.memory_id),
                    "sensitivity": fact.sensitivity,
                    "source": "acl_graphrag",
                },
            )
            for fact in graph_facts
        )
        return RetrievalBundle(memory_records, graph_facts, documents)

    @staticmethod
    def _query_terms(user_text: str) -> list[str]:
        terms = []
        for token in _TERM_PATTERN.findall(user_text):
            if token not in _STOPWORDS and token not in terms:
                terms.append(token)
            if len(terms) == 8:
                break
        return terms

