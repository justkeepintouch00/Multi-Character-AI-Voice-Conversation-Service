"""Run the C-mode goldset once and write JSONL results.

The script deliberately makes one Scene Director request per case. It performs
cheap structural checks locally and marks semantic checks for human review;
it does not call a second LLM as a judge.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


DEFAULT_GOLDSET = Path(__file__).resolve().parents[1] / "evals" / "20260812_1424_C_MODE_GOLDSET.jsonl"
DEFAULT_API_URL = "http://127.0.0.1:8000/api/v1/conversations"

GENERIC_CLOSING_PATTERNS = (
    "언제든 편하게 이야기하고 싶으실 때 말씀해",
    "필요하면 말씀해",
    "도와드릴게요",
)
ABSTRACT_QUESTION_PATTERNS = (
    "무엇이 가장 힘드",
    "어떤 점이 마음에 걸리",
    "무엇이 힘든",
)
MEDICAL_SPECULATION_PATTERNS = (
    "뇌에서 보상",
    "도파민 때문에",
    "정상입니다",
    "장애일 수",
)
RELATION_CONNECTOR_PATTERNS = (
    "맞아",
    "그렇지만",
    "그런데",
    "근데",
    "다만",
    "나는 조금",
    "나는 다르게",
    "그 말",
    "앞에서",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the C-mode Scene Director goldset")
    parser.add_argument("--goldset", type=Path, default=DEFAULT_GOLDSET)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--provider-label", default="groq")
    parser.add_argument("--model-label", default="openai-gpt-oss-120b")
    parser.add_argument("--dry-run", action="store_true", help="Validate cases without API calls")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--retry-rate-limit",
        action="store_true",
        help="Retry HTTP 429 only when Retry-After is present and at most 60 seconds",
    )
    parser.add_argument(
        "--capture-observability",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Store server metrics before and after each case in the result JSONL.",
    )
    return parser.parse_args()


def safe_filename_label(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-") or "unknown"


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number} JSON 오류: {exc}") from exc
        for field in ("case_id", "phase", "user_text", "must", "must_not"):
            if field not in case:
                raise ValueError(f"{path}:{line_number} 필수 필드 누락: {field}")
        if case["phase"] not in {"single", "multi"}:
            raise ValueError(f"{path}:{line_number} phase는 single 또는 multi여야 합니다.")
        cases.append(case)
    if not cases:
        raise ValueError(f"골드셋이 비어 있습니다: {path}")
    return cases


def check_case_shape(case: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if not str(case["user_text"]).strip():
        problems.append("user_text가 비어 있습니다")
    if not isinstance(case["must"], list) or not isinstance(case["must_not"], list):
        problems.append("must/must_not는 배열이어야 합니다")
    if case["phase"] == "multi" and len(case.get("history", [])) > 12:
        problems.append("history는 12개 이하여야 합니다")
    return problems


def score_response(case: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    scene_plan = payload.get("scene_plan", {}) if isinstance(payload, dict) else {}
    turns = scene_plan.get("turns", []) if isinstance(scene_plan, dict) else []
    texts = [str(turn.get("text", "")) for turn in turns if isinstance(turn, dict)]
    speakers = [str(turn.get("speaker_id", "")) for turn in turns if isinstance(turn, dict)]
    combined = " ".join(texts)
    max_score = 16 if case["phase"] == "single" else 24
    score = 0
    checks: dict[str, Any] = {}
    failures: list[str] = []

    valid_count = 1 <= len(turns) <= (1 if case["phase"] == "single" else 2)
    checks["turn_count"] = {"ok": valid_count, "value": len(turns)}
    score += 2 if valid_count else 0
    if not valid_count:
        failures.append("발화 수 제약 위반")

    unique_speakers = len(speakers) == len(set(speakers))
    checks["unique_speakers"] = {"ok": unique_speakers}
    score += 2 if unique_speakers else 0
    if not unique_speakers:
        failures.append("같은 캐릭터가 한 ScenePlan에서 중복 발화")

    concise = bool(texts) and all(1 <= len(text) <= 260 for text in texts)
    checks["concise"] = {"ok": concise, "character_lengths": [len(text) for text in texts]}
    score += 2 if concise else 0
    if not concise:
        failures.append("TTS 기준 발화가 지나치게 길거나 비어 있음")

    forbidden = []
    for pattern in GENERIC_CLOSING_PATTERNS + ABSTRACT_QUESTION_PATTERNS + MEDICAL_SPECULATION_PATTERNS:
        if pattern in combined:
            forbidden.append(pattern)
    checks["forbidden_patterns"] = {"ok": not forbidden, "matches": forbidden}
    score += 2 if not forbidden else 0
    if forbidden:
        failures.append("금지 표현 감지")

    if case["phase"] == "multi":
        has_relation = len(texts) < 2 or any(
            re.search(re.escape(pattern), texts[1])
            for pattern in RELATION_CONNECTOR_PATTERNS
        )
        checks["second_turn_reacts"] = {"ok": has_relation, "manual": True}
        score += 2 if has_relation else 0
        if not has_relation and len(texts) == 2:
            failures.append("두 번째 발화의 앞 캐릭터 반응 표현 부족")
        score += 2
        checks["different_viewpoint"] = {
            "ok": None,
            "manual": True,
            "note": "의견 차이와 맥락 이해는 사람이 확인",
        }

    manual_items = [
        "입력 핵심 이해",
        "감정 보정",
        "캐릭터 일관성",
        "대화 자연스러움",
        "응답 직접성",
        "기억·연속성",
    ]
    if case["phase"] == "multi":
        manual_items.extend(["화자 선택", "관점 차이"])
    checks["manual_review"] = manual_items
    return {
        "automatic_score": score,
        "automatic_max_score": max_score,
        "failures": failures,
        "checks": checks,
        "manual_review_required": True,
    }


def post_with_retry(
    client: httpx.Client,
    path: str,
    body: dict[str, Any],
    *,
    max_attempts: int = 5,
    retry_rate_limit: bool = False,
) -> dict[str, Any]:
    last_error: httpx.HTTPError | None = None
    for attempt in range(1, max_attempts + 1):
        response = client.post(path, json=body)
        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            if not retry_rate_limit or retry_after is None:
                response.raise_for_status()
            try:
                delay_seconds = float(retry_after)
            except (TypeError, ValueError):
                response.raise_for_status()
            if delay_seconds < 0 or delay_seconds > 60:
                response.raise_for_status()
            if attempt < max_attempts:
                time.sleep(delay_seconds)
                continue
            response.raise_for_status()
        if response.status_code < 500:
            response.raise_for_status()
            return response.json()
        last_error = httpx.HTTPStatusError(
            f"upstream error {response.status_code}",
            request=response.request,
            response=response,
        )
        if attempt < max_attempts:
            time.sleep(min(2**attempt, 20))
    assert last_error is not None
    raise last_error


def api_root(api_url: str) -> str:
    marker = "/conversations"
    if marker not in api_url:
        raise ValueError("api_url must end with /api/v1/conversations")
    return api_url.rsplit(marker, 1)[0]


def get_observability_snapshot(client: httpx.Client) -> dict[str, Any] | None:
    try:
        response = client.get(f"{api_root(str(client.base_url))}/observability/metrics")
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
        return None


def _counter_values(snapshot: dict[str, Any] | None) -> dict[tuple[str, tuple[tuple[str, str], ...]], float]:
    values: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
    for item in (snapshot or {}).get("counters", []):
        if not isinstance(item, dict):
            continue
        name, labels, value = item.get("name"), item.get("labels", {}), item.get("value")
        if isinstance(name, str) and isinstance(labels, dict) and isinstance(value, (int, float)):
            values[(name, tuple(sorted((str(k), str(v)) for k, v in labels.items())))] = float(value)
    return values


def observability_delta(before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any] | None:
    if before is None or after is None:
        return None
    previous, current = _counter_values(before), _counter_values(after)
    counters = [
        {"name": name, "labels": dict(labels), "value": round(value - previous.get((name, labels), 0), 6)}
        for (name, labels), value in current.items()
        if value - previous.get((name, labels), 0) != 0
    ]
    return {"counter_delta": sorted(counters, key=lambda item: (item["name"], sorted(item["labels"].items())))}


def create_seed_memories(client: httpx.Client, case: dict[str, Any], *, max_attempts: int, retry_rate_limit: bool) -> list[str]:
    raw_memories = case.get("seed_memories", [])
    if not isinstance(raw_memories, list):
        raise ValueError("seed_memories must be a JSON array")
    created_ids: list[str] = []
    for memory in raw_memories:
        if not isinstance(memory, dict):
            raise ValueError("seed_memories items must be objects")
        response = post_with_retry(client, f"{api_root(str(client.base_url))}/memories", memory, max_attempts=max_attempts, retry_rate_limit=retry_rate_limit)
        memory_id = response.get("id")
        if not isinstance(memory_id, str):
            raise ValueError("memory create response has no id")
        created_ids.append(memory_id)
    return created_ids


def delete_seed_memories(client: httpx.Client, memory_ids: list[str]) -> None:
    for memory_id in memory_ids:
        try:
            client.delete(f"{api_root(str(client.base_url))}/memories/{memory_id}").raise_for_status()
        except httpx.HTTPError:
            continue


def normalize_setup_messages(case: dict[str, Any]) -> list[dict[str, Any]]:
    raw = case.get("setup_messages", case.get("history", []))
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise ValueError("setup_messages/history must be a JSON array")
    return raw

def request_scene(client: httpx.Client, case: dict[str, Any], *, max_attempts: int = 5, retry_rate_limit: bool = False) -> tuple[dict[str, Any], list[str], dict[str, Any], list[dict[str, Any]]]:
    """Replay public setup messages and then run one scored user turn.

    A CHARACTER setup message can be the first message only (opening_message).
    USER setup messages go through the actual service, generating genuine public
    conversation history. Private facts must be passed through seed_memories.
    """
    configured_ids = case.get("character_ids")
    character_ids = [str(item) for item in configured_ids] if isinstance(configured_ids, list) and configured_ids else (["character_a"] if case["phase"] == "single" else ["character_a", "character_b"])
    setup_messages = normalize_setup_messages(case)
    opening_message: dict[str, Any] | None = None
    if setup_messages and setup_messages[0].get("role") == "CHARACTER":
        opening_message = {"speaker_id": setup_messages[0].get("speaker_id") or character_ids[0], "content": str(setup_messages[0].get("content", ""))}
        setup_messages = setup_messages[1:]
    if any(entry.get("role") != "USER" for entry in setup_messages):
        raise ValueError("setup_messages supports one initial CHARACTER opening and then USER messages only")
    create_payload: dict[str, Any] = {"mode": "TALK", "character_ids": character_ids}
    if opening_message:
        create_payload["opening_message"] = opening_message
    timings: dict[str, Any] = {"conversation_create_ms": 0, "seed_memory_ms": 0, "setup_message_ms": [], "scored_message_ms": 0, "conversation_read_ms": 0}
    started = time.perf_counter()
    conversation = post_with_retry(client, "", create_payload, max_attempts=max_attempts, retry_rate_limit=retry_rate_limit)
    timings["conversation_create_ms"] = round((time.perf_counter() - started) * 1000)
    conversation_id = conversation["id"]
    started = time.perf_counter()
    created_memory_ids = create_seed_memories(client, case, max_attempts=max_attempts, retry_rate_limit=retry_rate_limit)
    timings["seed_memory_ms"] = round((time.perf_counter() - started) * 1000)
    try:
        for entry in setup_messages:
            started = time.perf_counter()
            post_with_retry(client, f"/{conversation_id}/messages", {"content": str(entry.get("content", "")), "input_mode": "TEXT"}, max_attempts=max_attempts, retry_rate_limit=retry_rate_limit)
            timings["setup_message_ms"].append(round((time.perf_counter() - started) * 1000))
        started = time.perf_counter()
        payload = post_with_retry(client, f"/{conversation_id}/messages", {"content": case["user_text"], "input_mode": "TEXT"}, max_attempts=max_attempts, retry_rate_limit=retry_rate_limit)
        timings["scored_message_ms"] = round((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        messages_response = client.get(f"/{conversation_id}/messages", params={"limit": 100})
        messages_response.raise_for_status()
        messages_payload = messages_response.json()
        conversation_messages = messages_payload.get("messages", []) if isinstance(messages_payload, dict) else []
        if not isinstance(conversation_messages, list):
            conversation_messages = []
        timings["conversation_read_ms"] = round((time.perf_counter() - started) * 1000)
        return payload, created_memory_ids, timings, conversation_messages
    except Exception:
        delete_seed_memories(client, created_memory_ids)
        raise
def http_error_details(exc: httpx.HTTPError) -> dict[str, Any]:
    details: dict[str, Any] = {"error": str(exc)}
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        details["http_status"] = response.status_code
        retry_after = response.headers.get("retry-after")
        if retry_after is not None:
            details["retry_after"] = retry_after
        try:
            details["upstream_error"] = response.json()
        except json.JSONDecodeError:
            details["upstream_error"] = response.text[:2000]
    return details



def main() -> int:
    args = parse_args()
    cases = load_cases(args.goldset)
    timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    provider_label = safe_filename_label(args.provider_label)
    model_label = safe_filename_label(args.model_label)
    output = args.output or (
        Path(__file__).resolve().parents[1]
        / "evals"
        / "runs"
        / f"{timestamp}_c_mode_{provider_label}_{model_label}_results.jsonl"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter[str] = Counter()

    with httpx.Client(
        base_url=args.api_url, timeout=args.timeout, follow_redirects=True
    ) as client, output.open("w", encoding="utf-8") as handle:
        for case in cases:
            case_started = time.perf_counter()
            abort_after_case = False
            shape_problems = check_case_shape(case)
            result: dict[str, Any] = {
                "case_id": case["case_id"],
                "phase": case["phase"],
                "provider": args.provider_label,
                "model": args.model_label,
                "user_text": case["user_text"],
                "goldset": {
                    key: value
                    for key, value in case.items()
                    if key not in {"case_id", "phase", "user_text"}
                },
                "evaluated_at": datetime.now(timezone.utc).isoformat(),
                "request_status": "dry_run" if args.dry_run else "pending",
            }
            if shape_problems:
                result.update({"request_status": "invalid_case", "errors": shape_problems})
                counts["invalid_case"] += 1
            elif args.dry_run:
                result.update({"request_status": "dry_run", "automatic_score": None})
                counts["dry_run"] += 1
            else:
                try:
                    before_snapshot = get_observability_snapshot(client) if args.capture_observability else None
                    payload, seed_memory_ids, timings, conversation_messages = request_scene(client, case, retry_rate_limit=args.retry_rate_limit)
                    after_snapshot = get_observability_snapshot(client) if args.capture_observability else None
                    result.update({"request_status": "ok", "scene_plan": payload, "conversation_messages": conversation_messages, "timings": timings})
                    result["evaluation"] = score_response(case, payload)
                    if args.capture_observability:
                        result["observability"] = {"before": before_snapshot, "after": after_snapshot, "delta": observability_delta(before_snapshot, after_snapshot)}
                    delete_seed_memories(client, seed_memory_ids)
                    counts["ok"] += 1
                except httpx.HTTPError as exc:
                    result.update(http_error_details(exc))
                    status_code = result.get("http_status")
                    if status_code == 429:
                        result["request_status"] = "rate_limited"
                        counts["rate_limited"] += 1
                        abort_after_case = True
                    else:
                        result["request_status"] = "error"
                        counts["error"] += 1
                except ValueError as exc:
                    result.update({"request_status": "error", "error": str(exc)})
                    counts["error"] += 1
            result["completed_at"] = datetime.now(timezone.utc).isoformat()
            result["duration_ms"] = round((time.perf_counter() - case_started) * 1000)
            if isinstance(result.get("timings"), dict):
                result["timings"]["total_ms"] = result["duration_ms"]
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            handle.flush()
            if abort_after_case:
                break

    print(
        json.dumps(
            {
                "output": str(output),
                "provider": args.provider_label,
                "model": args.model_label,
                "cases": len(cases),
                "processed": sum(counts.values()),
                "counts": counts,
                "aborted": counts["rate_limited"] > 0,
            },
            ensure_ascii=False,
        )
    )
    return 0 if counts["error"] == 0 and counts["invalid_case"] == 0 and counts["rate_limited"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
