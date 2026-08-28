from __future__ import annotations

from time import perf_counter
from typing import TYPE_CHECKING, Any, AsyncIterator, Literal
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.observability import METRICS, log_event
from app.observability.context import get_trace_id
from app.observability.langsmith import finish_trace, trace_graph_node
from app.observability.observation import RuntimeObservation
from app.repositories.characters import DevelopmentContext
from app.schemas.message import ShareSuggestion
from app.schemas.scene_plan import RecentMessage, SceneTurn
from app.schemas.speaker_turn import MemoryContextItem, SpeakerTurnResult

if TYPE_CHECKING:
    from app.services.conversations import ConversationService, SpeakerSelection


class ConversationGraphState(TypedDict, total=False):
    context: DevelopmentContext
    conversation_id: UUID
    character_ids: list[str]
    memory_sharing_mode: str
    user_text: str
    recent_messages: list[RecentMessage]
    selection: object
    primary_result: SpeakerTurnResult
    primary_records: list
    primary_memory_context: list[MemoryContextItem]
    secondary_result: SpeakerTurnResult
    secondary_records: list
    secondary_memory_context: list[MemoryContextItem]
    turns: list[SceneTurn]
    share_suggestions: list[ShareSuggestion]
    observation: dict[str, Any]


class ConversationWorkflow:
    """Deterministic, inspectable 1–2 speaker conversation orchestration."""

    engine = "langgraph"

    def __init__(self, service: ConversationService) -> None:
        self.service = service
        builder = StateGraph(ConversationGraphState)
        builder.add_node("select_speakers", self._select_speakers)
        builder.add_node("retrieve_primary_context", self._retrieve_primary_context)
        builder.add_node("generate_primary", self._generate_primary)
        builder.add_node("store_primary_memory", self._store_primary_memory)
        builder.add_node("retrieve_secondary_context", self._retrieve_secondary_context)
        builder.add_node("generate_secondary", self._generate_secondary)
        builder.add_node("store_secondary_memory", self._store_secondary_memory)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "select_speakers")
        builder.add_conditional_edges(
            "select_speakers",
            self._primary_route,
            {
                "primary": "retrieve_primary_context",
                "primary_without_memory": "generate_primary",
                "empty": "finalize",
            },
        )
        builder.add_edge("retrieve_primary_context", "generate_primary")
        builder.add_edge("generate_primary", "store_primary_memory")
        builder.add_conditional_edges(
            "store_primary_memory",
            self._secondary_route,
            {
                "secondary": "retrieve_secondary_context",
                "secondary_without_memory": "generate_secondary",
                "finalize": "finalize",
            },
        )
        builder.add_edge("retrieve_secondary_context", "generate_secondary")
        builder.add_edge("generate_secondary", "store_secondary_memory")
        builder.add_edge("store_secondary_memory", "finalize")
        builder.add_edge("finalize", END)
        self.graph = builder.compile()

    async def run(
        self,
        *,
        context: DevelopmentContext,
        conversation_id: UUID,
        character_ids: list[str],
        memory_sharing_mode: str,
        user_text: str,
        recent_messages: list[RecentMessage],
    ) -> tuple[list[SceneTurn], list[ShareSuggestion]]:
        result = await self.graph.ainvoke(
            {
                "context": context,
                "conversation_id": conversation_id,
                "character_ids": character_ids,
                "memory_sharing_mode": memory_sharing_mode,
                "user_text": user_text,
                "recent_messages": recent_messages,
                "turns": [],
                "primary_records": [],
                "primary_memory_context": [],
                "secondary_records": [],
                "secondary_memory_context": [],
                "share_suggestions": [],
            }
        )
        return result.get("turns", []), result.get("share_suggestions", [])

    async def astream_events(
        self,
        *,
        context: DevelopmentContext,
        conversation_id: UUID,
        character_ids: list[str],
        memory_sharing_mode: str,
        user_text: str,
        recent_messages: list[RecentMessage],
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield privacy-safe node updates while retaining the final state."""
        initial: ConversationGraphState = {
            "context": context,
            "conversation_id": conversation_id,
            "character_ids": character_ids,
            "memory_sharing_mode": memory_sharing_mode,
            "user_text": user_text,
            "recent_messages": recent_messages,
            "turns": [],
            "primary_records": [],
            "primary_memory_context": [],
            "secondary_records": [],
            "secondary_memory_context": [],
            "share_suggestions": [],
            "observation": RuntimeObservation(trace_id=get_trace_id()).to_dict(),
        }
        state: dict[str, Any] = dict(initial)
        yield {"event": "workflow_started", "node": "workflow", "status": "started"}
        async for chunk in self.graph.astream(initial, stream_mode="updates"):
            updates = self._normalise_stream_chunk(chunk)
            for node, node_update in updates.items():
                if isinstance(node_update, dict):
                    state.update(node_update)
                yield {
                    "event": "node_completed",
                    "node": node,
                    "status": "completed",
                    "details": self._safe_node_details(node, state),
                }
        yield {
            "event": "workflow_completed",
            "node": "workflow",
            "status": "completed",
            "turns": [turn.model_dump(mode="json") for turn in state.get("turns", [])],
            "share_suggestions": [
                suggestion.model_dump(mode="json")
                for suggestion in state.get("share_suggestions", [])
            ],
            "observation": state.get("observation", {}),
        }

    @staticmethod
    def _normalise_stream_chunk(chunk: Any) -> dict[str, Any]:
        """Support LangGraph update chunks without exposing raw node output."""
        if isinstance(chunk, dict) and "type" in chunk and "data" in chunk:
            data = chunk.get("data")
            return data if isinstance(data, dict) else {}
        return chunk if isinstance(chunk, dict) else {}

    @staticmethod
    def _safe_node_details(node: str, state: dict[str, Any]) -> dict[str, Any]:
        details: dict[str, Any] = {}
        if node in {"retrieve_primary_context", "retrieve_secondary_context"}:
            role = "primary" if "primary" in node else "secondary"
            records = state.get(f"{role}_records", [])
            memory_context = state.get(f"{role}_memory_context", [])
            details["retrieved_memory_ids"] = list(
                dict.fromkeys(
                    [str(record.id) for record in records]
                    + [str(item.id) for item in memory_context]
                )
            )
            details["retrieved_count"] = len(details["retrieved_memory_ids"])
        elif node in {"generate_primary", "generate_secondary"}:
            role = "primary" if "primary" in node else "secondary"
            details["prompt_memory_ids"] = [
                str(item.id) for item in state.get(f"{role}_memory_context", [])
            ]
            details["turn_count"] = len(state.get("turns", []))
        elif node == "select_speakers":
            selection = state.get("selection")
            if selection:
                details["speaker_count"] = 2 if getattr(selection, "second_id", None) else 1
        return details

    async def _select_speakers(self, state: ConversationGraphState) -> dict:
        async def work() -> dict:
            character_ids = state["character_ids"]
            if not character_ids:
                return {"turns": [], "share_suggestions": []}
            selection = self.service._select_speakers(
                character_ids,
                state["context"].character_profiles,
                state["user_text"],
                state["recent_messages"],
            )
            return {"selection": selection}

        return await self._timed("select_speakers", work)

    def _primary_route(
        self, state: ConversationGraphState
    ) -> Literal["primary", "primary_without_memory", "empty"]:
        if not state.get("selection"):
            return "empty"
        if not any(message.role == "USER" for message in state.get("recent_messages", [])):
            return "primary_without_memory"
        return "primary"

    async def _retrieve_primary_context(self, state: ConversationGraphState) -> dict:
        async def work() -> dict:
            selection = state["selection"]
            records, memory_context = self.service._retrieve_turn_context(
                context=state["context"],
                conversation_id=state["conversation_id"],
                user_text=state["user_text"],
                speaker_id=selection.first_id,
                role="PRIMARY",
            )
            observation = dict(state.get("observation") or {})
            observation["retrieved_memory_ids"] = list(dict.fromkeys(
                [*observation.get("retrieved_memory_ids", []),
                 *[str(record.id) for record in records],
                 *[str(item.id) for item in memory_context]]
            ))
            return {"primary_records": records, "primary_memory_context": memory_context,
                    "observation": observation}

        return await self._timed("retrieve_primary_context", work)

    async def _generate_primary(self, state: ConversationGraphState) -> dict:
        async def work() -> dict:
            selection = state["selection"]
            context = state["context"]
            first_profile = context.character_profiles[selection.first_id]
            second_profile = (
                context.character_profiles[selection.second_id]
                if selection.second_id
                else None
            )
            result = await self.service._generate_turn(
                role="PRIMARY",
                context=context,
                user_text=state["user_text"],
                speaker_id=selection.first_id,
                speaker_profile=first_profile,
                other_participants=[second_profile] if second_profile else [],
                recent_messages=state["recent_messages"],
                turn_instruction=self.service._turn_instruction(selection, role="PRIMARY"),
                memory_context=state["primary_memory_context"],
            )
            suggestions = self.service._build_share_suggestions(
                result=result,
                records=state["primary_records"],
                speaker_id=selection.first_id,
                other_participants=[second_profile] if second_profile else [],
            )
            return {
                "primary_result": result,
                "turns": [self.service._to_scene_turn(result)],
                "share_suggestions": suggestions,
                "observation": {
                    **(state.get("observation") or {}),
                    "prompt_memory_ids": list(dict.fromkeys(
                        [str(item.id) for item in state.get("primary_memory_context", [])]
                    )),
                },
            }

        return await self._timed("generate_primary", work)

    async def _store_primary_memory(self, state: ConversationGraphState) -> dict:
        async def work() -> dict:
            self.service._maybe_store_extracted_memory(
                context=state["context"],
                conversation_id=state["conversation_id"],
                character_ids=state["character_ids"],
                memory_sharing_mode=state["memory_sharing_mode"],
                owner_character_id=state["selection"].first_id,
                result=state["primary_result"],
            )
            return {}

        return await self._timed("store_primary_memory", work)

    def _secondary_route(
        self, state: ConversationGraphState
    ) -> Literal["secondary", "secondary_without_memory", "finalize"]:
        selection = state["selection"]
        if not (
            selection.second_id
            and (selection.force_second or state["primary_result"].needs_second_speaker)
        ):
            return "finalize"
        if not any(message.role == "USER" for message in state.get("recent_messages", [])):
            return "secondary_without_memory"
        return "secondary"

    async def _retrieve_secondary_context(self, state: ConversationGraphState) -> dict:
        async def work() -> dict:
            selection = state["selection"]
            records, memory_context = self.service._retrieve_turn_context(
                context=state["context"],
                conversation_id=state["conversation_id"],
                user_text=state["user_text"],
                speaker_id=selection.second_id,
                role="SECONDARY",
            )
            observation = dict(state.get("observation") or {})
            observation["retrieved_memory_ids"] = list(dict.fromkeys(
                [*observation.get("retrieved_memory_ids", []),
                 *[str(record.id) for record in records],
                 *[str(item.id) for item in memory_context]]
            ))
            return {"secondary_records": records, "secondary_memory_context": memory_context,
                    "observation": observation}

        return await self._timed("retrieve_secondary_context", work)

    async def _generate_secondary(self, state: ConversationGraphState) -> dict:
        async def work() -> dict:
            selection = state["selection"]
            context = state["context"]
            first_profile = context.character_profiles[selection.first_id]
            secondary_recent = [
                *state["recent_messages"],
                RecentMessage(
                    role="CHARACTER",
                    speaker_id=selection.first_id,
                    content=state["primary_result"].text,
                ),
            ]
            result = await self.service._generate_turn(
                role="SECONDARY",
                context=context,
                user_text=state["user_text"],
                speaker_id=selection.second_id,
                speaker_profile=context.character_profiles[selection.second_id],
                other_participants=[first_profile],
                recent_messages=secondary_recent,
                turn_instruction=self.service._turn_instruction(selection, role="SECONDARY"),
                memory_context=state["secondary_memory_context"],
            )
            suggestions = self.service._build_share_suggestions(
                result=result,
                records=state["secondary_records"],
                speaker_id=selection.second_id,
                other_participants=[first_profile],
            )
            return {
                "secondary_result": result,
                "turns": [*state["turns"], self.service._to_scene_turn(result)],
                "share_suggestions": [*state["share_suggestions"], *suggestions],
                "observation": {
                    **(state.get("observation") or {}),
                    "prompt_memory_ids": list(dict.fromkeys(
                        [*(state.get("observation") or {}).get("prompt_memory_ids", []),
                         *[str(item.id) for item in state.get("secondary_memory_context", [])]]
                    )),
                },
            }

        return await self._timed("generate_secondary", work)

    async def _store_secondary_memory(self, state: ConversationGraphState) -> dict:
        async def work() -> dict:
            self.service._maybe_store_extracted_memory(
                context=state["context"],
                conversation_id=state["conversation_id"],
                character_ids=state["character_ids"],
                memory_sharing_mode=state["memory_sharing_mode"],
                owner_character_id=state["selection"].second_id,
                result=state["secondary_result"],
            )
            return {}

        return await self._timed("store_secondary_memory", work)

    async def _finalize(self, state: ConversationGraphState) -> dict:
        async def work() -> dict:
            turns = state.get("turns", [])
            selection = state.get("selection")
            path = (
                "primary_secondary_forced"
                if len(turns) == 2 and selection and selection.force_second
                else "primary_secondary" if len(turns) == 2 else "primary"
            )
            METRICS.increment("conversation_execution_paths_total", engine=self.engine, path=path)
            log_event(
                "conversation_execution_path",
                engine=self.engine,
                path=path,
                conversation_id=str(state["conversation_id"]),
            )
            return {}

        return await self._timed("finalize", work)

    async def _timed(self, node: str, work) -> dict:
        started = perf_counter()
        try:
            with trace_graph_node(
                name=f"LangGraph {node}",
                metadata={"node": node, "trace_id": get_trace_id()},
                tags=["langgraph", node],
            ) as trace_run:
                result = await work()
            finish_trace(trace_run, outputs=self._safe_trace_outputs(result))
            return result
        finally:
            METRICS.observe(
                "workflow_node_duration_ms",
                (perf_counter() - started) * 1000,
                engine=self.engine,
                node=node,
            )

    @staticmethod
    def _safe_trace_outputs(result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {}
        observation = result.get("observation")
        return {
            "updated_fields": sorted(key for key in result if key != "observation"),
            "observation": observation if isinstance(observation, dict) else {},
        }

