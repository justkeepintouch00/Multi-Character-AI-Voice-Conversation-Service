from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from time import perf_counter
from uuid import UUID

from app.observability import METRICS, log_event
from app.providers.base import (
    ProviderRequestError,
    ProviderTimeoutError,
    SceneDirectorProvider,
)
from app.repositories.characters import DevelopmentContext
from app.repositories.conversations import (
    ConversationRepository,
    ConversationSnapshot,
)
from app.rag.retriever import LangChainMemoryGraphRetriever, RetrievalRequest
from app.repositories.graph import GraphMemoryRepository
from app.repositories.memory import MemoryRecord, MemoryRepository
from app.workflows.conversation_graph import ConversationWorkflow
from app.schemas.conversation import ConversationCreate, ConversationRead
from app.schemas.message import (
    MessageCreate,
    MessageExchangeResponse,
    MessageListResponse,
    ShareSuggestion,
)
from app.schemas.scene_plan import RecentMessage, SceneCharacter, ScenePlan, SceneTurn
from app.schemas.speaker_turn import (
    MemoryContextItem,
    SpeakerTurnRequest,
    SpeakerTurnResult,
)
from app.services.errors import (
    InvalidResourceInputError,
    ResourceConflictError,
    ResourceNotFoundError,
)



@dataclass(frozen=True)
class SpeakerSelection:
    """Public-text routing result; it intentionally never includes memories."""

    first_id: str
    second_id: str | None
    force_second: bool = False
    routing_reason: str = "default"
class ConversationService:
    def __init__(
        self,
        repository: ConversationRepository,
        scene_director: SceneDirectorProvider,
        memory_repository: MemoryRepository,
        graph_repository: GraphMemoryRepository | None = None,
    ) -> None:
        self.repository = repository
        self.scene_director = scene_director
        self.memory_repository = memory_repository
        self.graph_repository = graph_repository
        self.memory_retriever = LangChainMemoryGraphRetriever(
            memory_repository, graph_repository
        )
        self.workflow = ConversationWorkflow(self)

    def create_conversation(self, request: ConversationCreate) -> ConversationRead:
        context = self.repository.ensure_development_context()
        unknown_ids = set(request.character_ids) - set(context.character_instance_ids)
        if unknown_ids:
            raise InvalidResourceInputError("지원하지 않는 character_id입니다.")
        snapshot = self.repository.create_conversation(
            context,
            request.mode,
            request.character_ids,
            request.opening_message,
            request.memory_sharing_mode,
        )
        return self._conversation_read(snapshot)

    def get_conversation(self, conversation_id: UUID) -> ConversationRead:
        context = self.repository.ensure_development_context()
        snapshot = self.repository.get_conversation(context.user_id, conversation_id)
        if snapshot is None:
            raise ResourceNotFoundError("대화를 찾을 수 없습니다.")
        return self._conversation_read(snapshot)

    def complete_conversation(self, conversation_id: UUID) -> ConversationRead:
        context = self.repository.ensure_development_context()
        current = self.repository.get_conversation(context.user_id, conversation_id)
        if current is None:
            raise ResourceNotFoundError("대화를 찾을 수 없습니다.")
        if current.status not in {"ACTIVE", "COMPLETED"}:
            raise ResourceConflictError("현재 상태에서는 대화를 완료할 수 없습니다.")
        snapshot = self.repository.complete_conversation(
            context.user_id, conversation_id
        )
        if snapshot is None:
            raise ResourceNotFoundError("대화를 찾을 수 없습니다.")
        return self._conversation_read(snapshot)

    async def create_message(
        self, conversation_id: UUID, request: MessageCreate
    ) -> MessageExchangeResponse:
        workflow_started = perf_counter()
        context = self.repository.ensure_development_context()
        conversation = self.repository.get_conversation(
            context.user_id, conversation_id
        )
        if conversation is None:
            raise ResourceNotFoundError("대화를 찾을 수 없습니다.")
        if conversation.status != "ACTIVE":
            raise ResourceConflictError("활성 상태의 대화에만 메시지를 보낼 수 있습니다.")

        user_message = self.repository.add_user_message(
            user_id=context.user_id,
            conversation_id=conversation_id,
            content=request.content,
            input_mode=request.input_mode,
        )
        recent_messages = self.repository.recent_messages(conversation_id)
        if recent_messages and recent_messages[-1].role == "USER":
            recent_messages = recent_messages[:-1]

        try:
            turns, share_suggestions = await self._generate_turns(
                context=context,
                conversation_id=conversation_id,
                character_ids=conversation.character_ids,
                memory_sharing_mode=conversation.memory_sharing_mode,
                user_text=request.content,
                recent_messages=recent_messages,
            )
            plan = ScenePlan(
                scene_action="CHARACTER_SEQUENCE",
                turns=turns,
                return_turn_to="USER",
                max_internal_turns=len(turns),
            )
            save_started = perf_counter()
            assistant_messages = self.repository.save_scene_result(
                context=context,
                conversation_id=conversation_id,
                triggering_message_id=user_message.id,
                plan=plan,
            )
            METRICS.observe(
                "workflow_node_duration_ms",
                (perf_counter() - save_started) * 1000,
                engine="langgraph",
                node="save_scene_plan",
            )
        except Exception as exc:
            duration_ms = (perf_counter() - workflow_started) * 1000
            METRICS.increment(
                "conversation_workflows_total", engine="langgraph", status="failed"
            )
            METRICS.observe(
                "conversation_workflow_duration_ms",
                duration_ms,
                engine="langgraph",
                status="failed",
            )
            log_event(
                "conversation_workflow_failed",
                level=logging.ERROR,
                conversation_id=str(conversation_id),
                engine="langgraph",
                duration_ms=round(duration_ms, 3),
                error_type=type(exc).__name__,
            )
            raise
        duration_ms = (perf_counter() - workflow_started) * 1000
        METRICS.increment(
            "conversation_workflows_total", engine="langgraph", status="completed"
        )
        METRICS.observe(
            "conversation_workflow_duration_ms",
            duration_ms,
            engine="langgraph",
            status="completed",
        )
        log_event(
            "conversation_workflow_completed",
            conversation_id=str(conversation_id),
            engine="langgraph",
            visible_turn_count=len(turns),
            duration_ms=round(duration_ms, 3),
        )
        return MessageExchangeResponse(
            user_message=user_message,
            scene_plan=plan,
            assistant_messages=assistant_messages,
            share_suggestions=share_suggestions,
        )

    async def create_message_stream(
        self, conversation_id: UUID, request: MessageCreate
    ) -> AsyncIterator[dict]:
        """Create a message and stream privacy-safe workflow progress events."""
        workflow_started = perf_counter()
        context = self.repository.ensure_development_context()
        conversation = self.repository.get_conversation(context.user_id, conversation_id)
        if conversation is None:
            raise ResourceNotFoundError("대화를 찾을 수 없습니다.")
        if conversation.status != "ACTIVE":
            raise ResourceConflictError("활성 상태의 대화에만 메시지를 보낼 수 있습니다.")

        user_message = self.repository.add_user_message(
            user_id=context.user_id,
            conversation_id=conversation_id,
            content=request.content,
            input_mode=request.input_mode,
        )
        recent_messages = self.repository.recent_messages(conversation_id)
        if recent_messages and recent_messages[-1].role == "USER":
            recent_messages = recent_messages[:-1]

        yield {
            "event": "message_accepted",
            "status": "completed",
            "user_message": user_message.model_dump(mode="json"),
        }
        final_event: dict | None = None
        try:
            async for event in self.workflow.astream_events(
                context=context,
                conversation_id=conversation_id,
                character_ids=conversation.character_ids,
                memory_sharing_mode=conversation.memory_sharing_mode,
                user_text=request.content,
                recent_messages=recent_messages,
            ):
                if event.get("event") == "workflow_completed":
                    final_event = event
                else:
                    yield event
            if final_event is None:
                raise RuntimeError("LangGraph 스트림이 최종 결과를 반환하지 않았습니다.")

            turns = [SceneTurn.model_validate(item) for item in final_event.get("turns", [])]
            share_suggestions = [
                ShareSuggestion.model_validate(item)
                for item in final_event.get("share_suggestions", [])
            ]
            plan = ScenePlan(
                scene_action="CHARACTER_SEQUENCE",
                turns=turns,
                return_turn_to="USER",
                max_internal_turns=len(turns),
            )
            save_started = perf_counter()
            assistant_messages = self.repository.save_scene_result(
                context=context,
                conversation_id=conversation_id,
                triggering_message_id=user_message.id,
                plan=plan,
            )
            METRICS.observe(
                "workflow_node_duration_ms",
                (perf_counter() - save_started) * 1000,
                engine="langgraph",
                node="save_scene_plan",
            )
            exchange = MessageExchangeResponse(
                user_message=user_message,
                scene_plan=plan,
                assistant_messages=assistant_messages,
                share_suggestions=share_suggestions,
            )
            observation = final_event.get("observation", {})
            log_event(
                "conversation_observation",
                conversation_id=str(conversation_id),
                engine="langgraph",
                observation=observation if isinstance(observation, dict) else {},
            )
            duration_ms = (perf_counter() - workflow_started) * 1000
            METRICS.increment("conversation_workflows_total", engine="langgraph", status="completed")
            METRICS.observe("conversation_workflow_duration_ms", duration_ms,
                            engine="langgraph", status="completed")
            log_event("conversation_workflow_completed", conversation_id=str(conversation_id),
                      engine="langgraph", visible_turn_count=len(turns),
                      duration_ms=round(duration_ms, 3), streaming=True)
            yield {
                "event": "workflow_completed",
                "status": "completed",
                "exchange": exchange.model_dump(mode="json"),
                "observation": observation if isinstance(observation, dict) else {},
            }
        except Exception as exc:
            duration_ms = (perf_counter() - workflow_started) * 1000
            METRICS.increment("conversation_workflows_total", engine="langgraph", status="failed")
            METRICS.observe("conversation_workflow_duration_ms", duration_ms,
                            engine="langgraph", status="failed")
            log_event("conversation_workflow_failed", level=logging.ERROR,
                      conversation_id=str(conversation_id), engine="langgraph",
                      duration_ms=round(duration_ms, 3), error_type=type(exc).__name__,
                      streaming=True)
            raise

    def list_messages(
        self, conversation_id: UUID, limit: int
    ) -> MessageListResponse:
        context = self.repository.ensure_development_context()
        conversation = self.repository.get_conversation(
            context.user_id, conversation_id
        )
        if conversation is None:
            raise ResourceNotFoundError("대화를 찾을 수 없습니다.")
        return MessageListResponse(
            items=self.repository.list_messages(conversation_id, limit)
        )

    async def _generate_turns(
        self,
        *,
        context: DevelopmentContext,
        conversation_id: UUID,
        character_ids: list[str],
        memory_sharing_mode: str,
        user_text: str,
        recent_messages: list[RecentMessage],
    ) -> tuple[list[SceneTurn], list[ShareSuggestion]]:
        """Run the explicit LangGraph conversation workflow."""
        return await self.workflow.run(
            context=context,
            conversation_id=conversation_id,
            character_ids=character_ids,
            memory_sharing_mode=memory_sharing_mode,
            user_text=user_text,
            recent_messages=recent_messages,
        )

    def _retrieve_turn_context(
        self,
        *,
        context: DevelopmentContext,
        conversation_id: UUID,
        user_text: str,
        speaker_id: str,
        role: str,
    ) -> tuple[list[MemoryRecord], list[MemoryContextItem]]:
        """Retrieve ACL-filtered memory through the LangChain runnable."""
        role_name = role.lower()
        started = perf_counter()
        bundle = self.memory_retriever.invoke(
            RetrievalRequest(
                user_id=context.user_id,
                viewer_character_instance_id=context.character_instance_ids[speaker_id],
                conversation_id=conversation_id,
                user_text=user_text,
            )
        )
        duration_ms = (perf_counter() - started) * 1000
        METRICS.increment("memory_searches_total", character_id=speaker_id, role=role_name)
        METRICS.observe("memory_search_result_count", len(bundle.memory_records),
                        character_id=speaker_id, role=role_name)
        METRICS.observe("graphrag_search_result_count", len(bundle.graph_facts),
                        character_id=speaker_id, role=role_name)
        METRICS.observe("workflow_node_duration_ms", duration_ms, engine="langgraph",
                        node=f"{role_name}_acl_retrieval")
        memory_context = [
            MemoryContextItem(id=str(record.id), content=record.content,
                              memory_type=record.memory_type, sensitivity=record.sensitivity)
            for record in bundle.memory_records
        ]
        existing_ids = {item.id for item in memory_context}
        for fact in bundle.graph_facts:
            if str(fact.memory_id) in existing_ids:
                continue
            memory_context.append(
                MemoryContextItem(id=str(fact.memory_id),
                                  content=f"[관계 그래프] {fact.text}",
                                  memory_type="RELATIONSHIP", sensitivity=fact.sensitivity)
            )
            existing_ids.add(str(fact.memory_id))
        return bundle.memory_records, memory_context

    async def _generate_turn(
        self,
        *,
        role: str,
        context: DevelopmentContext,
        user_text: str,
        speaker_id: str,
        speaker_profile: SceneCharacter,
        other_participants: list[SceneCharacter],
        recent_messages: list[RecentMessage],
        memory_context: list[MemoryContextItem],
        turn_instruction: str | None = None,
    ) -> SpeakerTurnResult:
        role_name = role.lower()
        provider_name = getattr(self.scene_director, "provider_name",
                                type(self.scene_director).__name__)
        model = getattr(self.scene_director, "model", "unknown")
        turn_request = SpeakerTurnRequest(
            role=role, user_text=user_text,
            user_display_name=context.user_display_name or None,
            speaker=speaker_profile, other_participants=other_participants,
            recent_messages=recent_messages, turn_instruction=turn_instruction,
            memory_context=memory_context,
        )
        llm_started = perf_counter()
        try:
            result = await self.scene_director.create_speaker_turn(turn_request)
        except Exception as exc:
            duration_ms = (perf_counter() - llm_started) * 1000
            upstream_status: int | str = "none"
            if isinstance(exc, ProviderRequestError):
                upstream_status = exc.status_code or "none"
                error_kind = str(exc.status_code or "request_error")
            elif isinstance(exc, ProviderTimeoutError):
                error_kind = "timeout"
            else:
                error_kind = type(exc).__name__
            METRICS.increment("llm_calls_total", provider=provider_name, model=model,
                              role=role_name, character_id=speaker_id, status="failed")
            METRICS.increment("llm_errors_total", provider=provider_name, model=model,
                              error=error_kind, upstream_status=upstream_status)
            METRICS.increment("character_response_failures_total",
                              character_id=speaker_id, provider=provider_name)
            METRICS.observe("llm_call_duration_ms", duration_ms, provider=provider_name,
                            model=model, role=role_name, status="failed")
            log_event("llm_call_failed", level=logging.ERROR, provider=provider_name,
                      model=model, role=role_name, character_id=speaker_id,
                      duration_ms=round(duration_ms, 3), error_type=type(exc).__name__,
                      upstream_status=upstream_status)
            raise
        duration_ms = (perf_counter() - llm_started) * 1000
        METRICS.increment("llm_calls_total", provider=provider_name, model=model,
                          role=role_name, character_id=speaker_id, status="success")
        METRICS.observe("llm_call_duration_ms", duration_ms, provider=provider_name,
                        model=model, role=role_name, status="success")
        log_event("llm_call_completed", provider=provider_name, model=model,
                  role=role_name, character_id=speaker_id,
                  duration_ms=round(duration_ms, 3), memory_count=len(memory_context))
        return result

    def _build_share_suggestions(
        self,
        *,
        result: SpeakerTurnResult,
        records: list[MemoryRecord],
        speaker_id: str,
        other_participants: list[SceneCharacter],
    ) -> list[ShareSuggestion]:
        if not result.disclosed_memory_ids or not other_participants:
            return []
        records_by_id = {str(record.id): record for record in records}
        to_character_id = other_participants[0].id
        suggestions: list[ShareSuggestion] = []
        for raw_id in result.disclosed_memory_ids:
            record = records_by_id.get(raw_id)
            # The schema already constrains disclosed_memory_ids to ids that
            # were on this request, but a record lookup miss is tolerated
            # rather than trusted blindly -- never surface a suggestion for
            # a memory we can't independently confirm the speaker actually had.
            if record is None:
                continue
            suggestions.append(
                ShareSuggestion(
                    memory_id=record.id,
                    from_character_id=speaker_id,
                    to_character_id=to_character_id,
                    content_preview=record.content[:120],
                )
            )
        return suggestions

    def _maybe_store_extracted_memory(
        self,
        *,
        context: DevelopmentContext,
        conversation_id: UUID,
        character_ids: list[str],
        memory_sharing_mode: str,
        owner_character_id: str,
        result: SpeakerTurnResult,
    ) -> None:
        if not result.extracted_memory.has_memory:
            return
        content = result.extracted_memory.content.strip()
        if not content:
            return
        readable_by_ids = self._readable_by_for_new_memory(
            memory_sharing_mode=memory_sharing_mode,
            character_ids=character_ids,
            owner_character_id=owner_character_id,
        )
        memory_record = self.memory_repository.create_memory(
            user_id=context.user_id,
            content=content,
            memory_type="RELATIONSHIP",
            owner_character_instance_id=context.character_instance_ids[
                owner_character_id
            ],
            sensitivity=result.extracted_memory.sensitivity,
            granted_by_user_id=context.user_id,
            readable_by=[
                context.character_instance_ids[character_id]
                for character_id in readable_by_ids
            ],
            source_conversation_id=conversation_id,
        )
        relation = result.extracted_memory.graph_relation
        if (
            self.graph_repository is not None
            and relation.has_relation
            and relation.source_entity.strip()
            and relation.relation.strip()
            and relation.target_entity.strip()
        ):
            self.graph_repository.create_edge(
                user_id=context.user_id,
                memory_id=memory_record.id,
                source_entity=relation.source_entity,
                relation=relation.relation,
                target_entity=relation.target_entity,
                summary=relation.summary or None,
            )

    @staticmethod
    def _readable_by_for_new_memory(
        *,
        memory_sharing_mode: str,
        character_ids: list[str],
        owner_character_id: str,
    ) -> list[str]:
        if len(character_ids) < 2:
            return [owner_character_id]
        first_id, second_id = character_ids[0], character_ids[1]
        if memory_sharing_mode == "SHARED":
            return [first_id, second_id]
        if memory_sharing_mode == "FIRST_ONLY" and owner_character_id == first_id:
            return [first_id, second_id]
        if memory_sharing_mode == "SECOND_ONLY" and owner_character_id == second_id:
            return [first_id, second_id]
        return [owner_character_id]

    @staticmethod
    def _speaker_aliases(character_id: str, profile: SceneCharacter) -> list[str]:
        aliases = [character_id]
        if profile.name:
            aliases.append(profile.name)
        if character_id == "character_a":
            aliases.append("A")
        elif character_id == "character_b":
            aliases.append("B")
        return aliases

    @classmethod
    def _mentions_character(
        cls, user_text: str, character_id: str, profile: SceneCharacter
    ) -> bool:
        for alias in cls._speaker_aliases(character_id, profile):
            if len(alias) == 1 and alias.isascii():
                if re.search(rf"(?<![A-Za-z0-9_]){re.escape(alias)}(?![A-Za-z0-9_])", user_text):
                    return True
            elif alias and alias in user_text:
                return True
        return False

    @classmethod
    def _select_speakers(
        cls,
        character_ids: list[str],
        character_profiles: dict[str, SceneCharacter],
        user_text: str,
        recent_messages: list[RecentMessage],
    ) -> SpeakerSelection:
        if len(character_ids) == 1:
            return SpeakerSelection(first_id=character_ids[0], second_id=None)

        mentioned_ids = [
            character_id
            for character_id in character_ids
            if cls._mentions_character(user_text, character_id, character_profiles[character_id])
        ]
        last_speaker_id = next(
            (
                message.speaker_id
                for message in reversed(recent_messages)
                if message.role == "CHARACTER" and message.speaker_id in character_ids
            ),
            None,
        )
        # "A가 아니라 B가 말해" means B speaks. If A actually just spoke,
        # retain A for one acknowledgement before B, matching the user's
        # correction; otherwise do not manufacture an apology.
        correction_from: str | None = None
        correction_to: str | None = None
        for from_id in character_ids:
            for to_id in character_ids:
                if from_id == to_id:
                    continue
                for from_alias in cls._speaker_aliases(from_id, character_profiles[from_id]):
                    for to_alias in cls._speaker_aliases(to_id, character_profiles[to_id]):
                        pattern = (
                            rf"{re.escape(from_alias)}(?:가|은|는)?\s*아니라\s*"
                            rf"{re.escape(to_alias)}(?:가|은|는)?"
                        )
                        if re.search(pattern, user_text, flags=re.IGNORECASE):
                            correction_from, correction_to = from_id, to_id
                            break
                    if correction_to:
                        break
                if correction_to:
                    break
            if correction_to:
                break
        if correction_to:
            if last_speaker_id == correction_from:
                return SpeakerSelection(
                    first_id=correction_from,
                    second_id=correction_to,
                    force_second=True,
                    routing_reason="correction_acknowledgement",
                )
            return SpeakerSelection(
                first_id=correction_to,
                second_id=next(item for item in character_ids if item != correction_to),
                routing_reason="explicit_correction_target",
            )

        if len(mentioned_ids) >= 2 and re.search(r"(?:둘\s*다|모두|각각|함께)", user_text):
            return SpeakerSelection(
                first_id=last_speaker_id or character_ids[0],
                second_id=next(item for item in character_ids if item != (last_speaker_id or character_ids[0])),
                force_second=True,
                routing_reason="explicit_all_speakers",
            )
        if len(mentioned_ids) == 1:
            first_id = mentioned_ids[0]
        else:
            first_id = last_speaker_id or character_ids[0]
        return SpeakerSelection(
            first_id=first_id,
            second_id=next(item for item in character_ids if item != first_id),
            routing_reason="explicit_name" if len(mentioned_ids) == 1 else "last_speaker_or_default",
        )

    @staticmethod
    def _turn_instruction(selection: SpeakerSelection, *, role: str) -> str | None:
        if selection.routing_reason == "explicit_all_speakers":
            return (
                "사용자가 두 캐릭터 모두의 실제 대사를 요청했다. 요청을 설명하거나 "
                "되풀이하지 말고, 각자 한두 문장으로 자연스럽게 답한다."
            )
        if selection.routing_reason == "correction_acknowledgement":
            if role == "PRIMARY":
                return "사용자가 방금 당신이 아니라 다른 캐릭터에게 답하라고 정정했다. 변명 없이 한 문장으로 짧게 인정하거나 사과하고 끝낸다."
            return "사용자가 당신에게 발화권을 넘겼다. 앞 캐릭터의 짧은 인정 뒤에, 현재 대화 주제에 직접 답한다."
        if selection.routing_reason == "explicit_correction_target":
            return "사용자가 당신에게 직접 답하라고 지목했다. 다른 캐릭터의 사과나 설명을 대신하지 말고 현재 대화 주제에 직접 답한다."
        return None

    @classmethod
    def _order_speakers(
        cls,
        character_ids: list[str],
        character_profiles: dict[str, SceneCharacter],
        user_text: str,
        recent_messages: list[RecentMessage],
    ) -> tuple[str, str | None]:
        """Backward-compatible view used by existing callers and tests."""
        selection = cls._select_speakers(
            character_ids, character_profiles, user_text, recent_messages
        )
        return selection.first_id, selection.second_id
    @staticmethod
    def _to_scene_turn(result: SpeakerTurnResult) -> SceneTurn:
        return SceneTurn(
            speaker_id=result.speaker_id,
            to=result.to,
            emotion=result.emotion,
            text=result.text,
        )

    @staticmethod
    def _conversation_read(snapshot: ConversationSnapshot) -> ConversationRead:
        return ConversationRead(
            id=snapshot.id,
            mode=snapshot.mode,
            status=snapshot.status,
            character_ids=snapshot.character_ids,
            memory_sharing_mode=snapshot.memory_sharing_mode,
            created_at=snapshot.created_at,
            updated_at=snapshot.updated_at,
            closed_at=snapshot.closed_at,
        )
