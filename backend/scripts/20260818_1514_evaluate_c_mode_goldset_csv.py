"""Run the existing C-mode evaluator with the CSV goldset.

The evaluator currently consumes JSONL. This adapter keeps the evaluator
unchanged while accepting the human-editable CSV dataset and converting it to
temporary JSONL at runtime.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLDSET = ROOT / "evals" / "20260820_153027_C_MODE_FAILED13_RETEST.csv"
EVALUATOR = Path(__file__).with_name("20260812_1440_evaluate_c_mode_goldset.py")
REQUIRED_FIELDS = ("case_id", "phase", "user_text", "history", "must", "must_not")
# Keep every column in the editable CSV. The evaluator only requires the
# fields above, but the remaining expected-behaviour columns must survive into
# the JSONL result so the review dashboard can show what each case intended.
JSON_FIELDS = {"history", "setup_messages", "seed_memories", "must", "must_not", "character_ids", "expected_speaker_ids"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the C-mode CSV goldset")
    parser.add_argument("--goldset", type=Path, default=DEFAULT_GOLDSET)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000/api/v1/conversations")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--provider-label", default="groq")
    parser.add_argument("--model-label", default="openai-gpt-oss-120b")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--retry-rate-limit", action="store_true")
    parser.add_argument("--capture-observability", action="store_true")
    return parser.parse_args()


def csv_to_jsonl(source: Path, target: Path) -> int:
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        missing = set(REQUIRED_FIELDS) - set(rows.fieldnames or [])
        if missing:
            raise ValueError(f"CSV 필수 필드 누락: {', '.join(sorted(missing))}")
        cases = []
        for line_number, row in enumerate(rows, 2):
            case = dict(row)
            for field in JSON_FIELDS:
                try:
                    case[field] = json.loads(case.get(field) or "[]")
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"{source}:{line_number} {field} JSON 오류: {exc}"
                    ) from exc
            cases.append(case)
    if not cases:
        raise ValueError(f"CSV 골드셋이 비어 있습니다: {source}")
    target.write_text(
        "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases),
        encoding="utf-8",
    )
    return len(cases)


def main() -> int:
    args = parse_args()
    with tempfile.TemporaryDirectory(prefix="c-mode-goldset-") as temporary:
        jsonl_path = Path(temporary) / "goldset.jsonl"
        count = csv_to_jsonl(args.goldset, jsonl_path)
        command = [
            sys.executable,
            str(EVALUATOR),
            "--goldset",
            str(jsonl_path),
            "--api-url",
            args.api_url,
            "--timeout",
            str(args.timeout),
            "--provider-label",
            args.provider_label,
            "--model-label",
            args.model_label,
        ]
        if args.output:
            command.extend(["--output", str(args.output)])
        if args.dry_run:
            command.append("--dry-run")
        if args.retry_rate_limit:
            command.append("--retry-rate-limit")
        if args.capture_observability:
            command.append("--capture-observability")
        print(f"CSV cases: {count}")
        return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())

