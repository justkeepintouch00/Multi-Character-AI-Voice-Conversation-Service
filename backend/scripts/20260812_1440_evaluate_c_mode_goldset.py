"""Run the C-mode goldset once and write JSONL results.

The script deliberately makes one Scene Director request per case. It performs
cheap structural checks locally and marks semantic checks for human review;
it does not call a second LLM as a judge.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


DEFAULT_GOLDSET = Path(__file__).resolve().parents[1] / "evals" / "20260812_1424_C_MODE_GOLDSET.jsonl"
DEFAULT_API_URL = "http://127.0.0.1:8000/api/v1/scene-plans"

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
    parser.add_argument("--dry-run", action="store_true", help="Validate cases without API calls")
    parser.add_argument("--timeout", type=float, default=60.0)
    return parser.parse_args()


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


def recent_messages(case: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for message in case.get("history", []):
        role = message.get("role", "USER")
        normalized.append(
            {
                "role": role if role in {"USER", "CHARACTER"} else "USER",
                "speaker_id": message.get("speaker_id"),
                "content": str(message["content"]),
            }
        )
    return normalized


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
    turns = payload.get("turns", []) if isinstance(payload, dict) else []
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


def request_scene(client: httpx.Client, case: dict[str, Any]) -> dict[str, Any]:
    character_ids = ["character_a"] if case["phase"] == "single" else ["character_a", "character_b"]
    response = client.post(
        "",
        json={
            "user_text": case["user_text"],
            "character_ids": character_ids,
            "recent_messages": recent_messages(case),
        },
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    args = parse_args()
    cases = load_cases(args.goldset)
    timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    output = args.output or Path(__file__).resolve().parents[1] / "evals" / "runs" / f"{timestamp}_c_mode_results.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter[str] = Counter()

    with httpx.Client(base_url=args.api_url, timeout=args.timeout) as client, output.open("w", encoding="utf-8") as handle:
        for case in cases:
            shape_problems = check_case_shape(case)
            result: dict[str, Any] = {
                "case_id": case["case_id"],
                "phase": case["phase"],
                "user_text": case["user_text"],
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
                    payload = request_scene(client, case)
                    result.update({"request_status": "ok", "scene_plan": payload})
                    result["evaluation"] = score_response(case, payload)
                    counts["ok"] += 1
                except (httpx.HTTPError, ValueError) as exc:
                    result.update({"request_status": "error", "error": str(exc)})
                    counts["error"] += 1
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")

    print(json.dumps({"output": str(output), "cases": len(cases), "counts": counts}, ensure_ascii=False))
    return 0 if counts["error"] == 0 and counts["invalid_case"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
