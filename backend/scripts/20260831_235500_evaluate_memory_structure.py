"""Replay the C-mode conversations and compare persisted memory structures.

This is intentionally separate from the ACL evaluator.  It records the
memory_items and memory_graph_edges created by each conversation for one
policy version, then reports structural health metrics.  It does not invent a
semantic gold label: precision/recall for memory meaning require a separately
annotated structure goldset.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import (
    get_database_url,
    get_development_user_display_name,
    get_development_user_external_id,
)
from app.db.models import MemoryGraphEdge, MemoryItem
from app.repositories.characters import SQLAlchemyCharacterRepository


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLDSET = ROOT / "evals" / "20260831_181500_C_MODE_BAKUGO_SHINGOO.csv"
DEFAULT_API_URL = "http://127.0.0.1:8001/api/v1/conversations"
VALID_MEMORY_TYPES = {
    "USER_GLOBAL",
    "RELATIONSHIP",
    "GROUP",
    "CHARACTER_INTERNAL",
    "PROFILE",
    "EPISODE",
}


def parse_json(value: str | None, default: Any) -> Any:
    if not value or not value.strip():
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"골드셋이 비어 있습니다: {path}")
    cases: list[dict[str, Any]] = []
    for row in rows:
        row["character_ids"] = parse_json(row.get("character_ids"), [])
        row["setup_messages"] = parse_json(row.get("setup_messages"), [])
        row["seed_memories"] = parse_json(row.get("seed_memories"), [])
        cases.append(row)
    return cases


def api_root(api_url: str) -> str:
    marker = "/conversations"
    if marker not in api_url:
        raise ValueError("api_url은 /api/v1/conversations로 끝나야 합니다.")
    return api_url.rsplit(marker, 1)[0]


def post_with_retry(client: httpx.Client, path: str, body: dict[str, Any], attempts: int = 3) -> dict[str, Any]:
    last: httpx.HTTPError | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = client.post(path, json=body)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("API 응답이 객체가 아닙니다.")
            return payload
        except httpx.HTTPError as exc:
            last = exc
            if attempt < attempts:
                time.sleep(min(2**attempt, 8))
    assert last is not None
    raise last


def create_seed_memories(client: httpx.Client, case: dict[str, Any]) -> list[str]:
    created: list[str] = []
    for memory in case.get("seed_memories", []):
        if not isinstance(memory, dict):
            continue
        payload = post_with_retry(client, f"{api_root(str(client.base_url))}/memories", memory)
        if isinstance(payload.get("id"), str):
            created.append(payload["id"])
    return created


def delete_via_api(client: httpx.Client, ids: list[str]) -> None:
    for memory_id in ids:
        try:
            client.delete(f"{api_root(str(client.base_url))}/memories/{memory_id}").raise_for_status()
        except httpx.HTTPError:
            continue


def normalize_setup(case: dict[str, Any], character_ids: list[str]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    setup = case.get("setup_messages") or []
    if not isinstance(setup, list):
        return None, []
    opening: dict[str, Any] | None = None
    if setup and isinstance(setup[0], dict) and setup[0].get("role") == "CHARACTER":
        opening = {
            "speaker_id": setup[0].get("speaker_id") or (character_ids[0] if character_ids else "character_a"),
            "content": str(setup[0].get("content") or ""),
        }
        setup = setup[1:]
    return opening, [entry for entry in setup if isinstance(entry, dict) and entry.get("role") == "USER"]


def run_case(client: httpx.Client, case: dict[str, Any]) -> tuple[str, list[str], dict[str, Any], list[dict[str, Any]]]:
    character_ids = [str(item) for item in case.get("character_ids", []) if item]
    if not character_ids:
        character_ids = ["character_a"] if case.get("phase") == "single" else ["character_a", "character_b"]
    opening, setup = normalize_setup(case, character_ids)
    create_payload: dict[str, Any] = {"mode": "TALK", "character_ids": character_ids}
    if opening:
        create_payload["opening_message"] = opening
    conversation = post_with_retry(client, "", create_payload)
    conversation_id = str(conversation["id"])
    seed_ids = create_seed_memories(client, case)
    try:
        for entry in setup:
            post_with_retry(client, f"/{conversation_id}/messages", {"content": str(entry.get("content") or ""), "input_mode": "TEXT"})
        response = post_with_retry(client, f"/{conversation_id}/messages", {"content": str(case.get("user_text") or ""), "input_mode": "TEXT"})
        messages_response = client.get(f"/{conversation_id}/messages", params={"limit": 100})
        messages_response.raise_for_status()
        items = messages_response.json().get("items", [])
        return conversation_id, seed_ids, response, items if isinstance(items, list) else []
    except Exception:
        delete_via_api(client, seed_ids)
        raise


def snapshot_memory(session: Session, conversation_id: str, policy: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    memory_rows = list(session.scalars(select(MemoryItem).where(
        MemoryItem.source_conversation_id == conversation_id,
        MemoryItem.policy_version == policy,
    )))
    ids = [item.id for item in memory_rows]
    edge_rows = list(session.scalars(select(MemoryGraphEdge).where(MemoryGraphEdge.memory_id.in_(ids)))) if ids else []
    memories = [{
        "id": str(item.id),
        "memory_type": item.memory_type,
        "content": item.content,
        "policy_version": item.policy_version,
        "status": item.status,
        "confidence": float(item.confidence),
        "owner_character_instance_id": str(item.owner_character_instance_id) if item.owner_character_instance_id else None,
        "source_conversation_id": str(item.source_conversation_id) if item.source_conversation_id else None,
        "metadata": item.metadata_json or {},
        "supersedes_memory_id": str(item.supersedes_memory_id) if item.supersedes_memory_id else None,
    } for item in memory_rows]
    edges = [{
        "id": str(edge.id),
        "memory_id": str(edge.memory_id),
        "source_entity": edge.source_entity,
        "relation": edge.relation,
        "target_entity": edge.target_entity,
        "summary": edge.summary,
        "policy_version": edge.policy_version,
        "status": edge.status,
        "confidence": float(edge.confidence),
        "source_memory_id": str(edge.memory_id),
        "supersedes_edge_id": str(edge.supersedes_edge_id) if edge.supersedes_edge_id else None,
    } for edge in edge_rows]
    return memories, edges


def cleanup_conversation_memories(session: Session, conversation_id: str, policy: str) -> None:
    ids = list(session.scalars(select(MemoryItem.id).where(
        MemoryItem.source_conversation_id == conversation_id,
        MemoryItem.policy_version == policy,
    )))
    if ids:
        session.execute(delete(MemoryGraphEdge).where(MemoryGraphEdge.memory_id.in_(ids)))
        session.execute(delete(MemoryItem).where(MemoryItem.id.in_(ids)))
        session.commit()


def structural_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    memories = [memory for case in cases for memory in case.get("memories", [])]
    edges = [edge for case in cases for edge in case.get("graph_edges", [])]
    type_counts = Counter(memory["memory_type"] for memory in memories)
    content_counts = Counter(re.sub(r"\s+", " ", memory["content"].strip().lower()) for memory in memories if memory.get("content"))
    duplicate_records = sum(count - 1 for count in content_counts.values() if count > 1)
    with_memories = [case for case in cases if case.get("memories")]
    cases_with_edges = sum(1 for case in with_memories if case.get("graph_edges"))
    valid_owner = sum(
        1 for memory in memories
        if memory["memory_type"] in {"PROFILE", "EPISODE", "USER_GLOBAL", "GROUP"}
        or memory.get("owner_character_instance_id")
    )
    return {
        "cases_total": len(cases),
        "cases_succeeded": sum(1 for case in cases if case.get("request_status") == "ok"),
        "cases_failed": sum(1 for case in cases if case.get("request_status") != "ok"),
        "memory_records_total": len(memories),
        "memory_records_per_case": round(len(memories) / len(cases), 3) if cases else 0.0,
        "memory_type_counts": dict(sorted(type_counts.items())),
        "memory_type_distribution": {key: round(value / len(memories), 4) for key, value in sorted(type_counts.items())} if memories else {},
        "valid_memory_type_rate": round(sum(memory.get("memory_type") in VALID_MEMORY_TYPES for memory in memories) / len(memories), 4) if memories else 1.0,
        "owner_constraint_rate": round(valid_owner / len(memories), 4) if memories else 1.0,
        "source_conversation_coverage": round(sum(memory.get("source_conversation_id") is not None for memory in memories) / len(memories), 4) if memories else 1.0,
        "policy_version_consistency": round(sum(memory.get("policy_version") == (cases[0].get("policy_version") if cases else None) for memory in memories) / len(memories), 4) if memories else 1.0,
        "superseded_link_rate": round(sum(bool(memory.get("supersedes_memory_id")) for memory in memories) / len(memories), 4) if memories else 0.0,
        "duplicate_content_rate": round(duplicate_records / len(memories), 4) if memories else 0.0,
        "graph_edges_total": len(edges),
        "graph_edge_case_coverage": round(cases_with_edges / len(with_memories), 4) if with_memories else 0.0,
        "graph_edge_valid_rate": round(sum(bool(edge.get("source_entity") and edge.get("relation") and edge.get("target_entity") and edge.get("source_memory_id")) for edge in edges) / len(edges), 4) if edges else 1.0,
        "summary_field_presence_rate": 0.0,
        "semantic_precision_recall_f1": None,
    }


def evaluation_database_url() -> str:
    configured = make_url(get_database_url())
    return str(configured.set(database="character_companion_eval"))


def compare_reports(first_path: Path, second_path: Path, output: Path | None) -> Path:
    first, second = json.loads(first_path.read_text(encoding="utf-8")), json.loads(second_path.read_text(encoding="utf-8"))
    a, b = first["metrics"], second["metrics"]
    numeric_keys = [key for key, value in a.items() if isinstance(value, (int, float)) and isinstance(b.get(key), (int, float))]
    report = {
        "dataset_type": "memory_structure_comparison",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline": {"policy_version": first.get("policy_version"), "file": str(first_path), "metrics": a},
        "candidate": {"policy_version": second.get("policy_version"), "file": str(second_path), "metrics": b},
        "delta_candidate_minus_baseline": {key: round(float(b[key]) - float(a[key]), 4) for key in numeric_keys},
        "semantic_precision_recall_f1": None,
        "note": "구조 건강 지표 비교입니다. 의미 정확도의 Precision/Recall/F1은 별도 주석 골드셋이 필요합니다.",
    }
    destination = output or (ROOT / "evals" / "runs" / f"{datetime.now().astimezone().strftime('%Y%m%d_%H%M%S')}_memory_structure_comparison.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(destination), **report["delta_candidate_minus_baseline"]}, ensure_ascii=False, indent=2))
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy-version", choices=["v1", "v2"], default="v1")
    parser.add_argument("--goldset", type=Path, default=DEFAULT_GOLDSET)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare", nargs=2, type=Path)
    args = parser.parse_args()
    if args.compare:
        compare_reports(args.compare[0], args.compare[1], args.output)
        return 0

    cases = load_cases(args.goldset)
    engine = create_engine(args.database_url or evaluation_database_url(), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    session = SessionLocal()
    report_cases: list[dict[str, Any]] = []
    try:
        context = SQLAlchemyCharacterRepository(
            session,
            development_user_external_id=get_development_user_external_id() or "local-evaluation-user",
            development_user_display_name=get_development_user_display_name(),
        ).ensure_development_context()
        with httpx.Client(base_url=args.api_url, timeout=240.0, follow_redirects=True) as client:
            for case in cases:
                result: dict[str, Any] = {
                    "case_id": case.get("case_id"),
                    "user_text": case.get("user_text"),
                    "policy_version": args.policy_version,
                    "request_status": "pending",
                    "memories": [],
                    "graph_edges": [],
                }
                conversation_id: str | None = None
                seed_ids: list[str] = []
                try:
                    conversation_id, seed_ids, response, messages = run_case(client, case)
                    memories, edges = snapshot_memory(session, conversation_id, args.policy_version)
                    result.update({
                        "request_status": "ok",
                        "conversation_id": conversation_id,
                        "response_turn_count": len((response.get("scene_plan") or {}).get("turns", [])),
                        "conversation_message_count": len(messages),
                        "memories": memories,
                        "graph_edges": edges,
                    })
                except Exception as exc:
                    result.update({"request_status": "error", "error": f"{type(exc).__name__}: {exc}"})
                finally:
                    if conversation_id:
                        cleanup_conversation_memories(session, conversation_id, args.policy_version)
                    delete_via_api(client, seed_ids)
                report_cases.append(result)
    finally:
        session.close()
        engine.dispose()

    report = {
        "dataset_type": "memory_structure_evaluation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy_version": args.policy_version,
        "goldset_file": str(args.goldset),
        "cases": report_cases,
        "metrics": structural_metrics(report_cases),
        "semantic_metrics": None,
        "note": "ACL 권한 평가는 별도 보고서입니다. 이 결과는 DB에 실제 저장된 메모리·그래프 구조의 건강 지표입니다.",
    }
    output = args.output or (ROOT / "evals" / "runs" / f"{datetime.now().astimezone().strftime('%Y%m%d_%H%M%S')}_memory_structure_{args.policy_version}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "policy_version": args.policy_version, **report["metrics"]}, ensure_ascii=False, indent=2))
    return 0 if report["metrics"]["cases_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
