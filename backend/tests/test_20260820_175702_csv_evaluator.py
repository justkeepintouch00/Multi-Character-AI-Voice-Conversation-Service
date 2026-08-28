from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "20260818_1514_evaluate_c_mode_goldset_csv.py"
)


def load_csv_adapter():
    spec = importlib.util.spec_from_file_location("c_mode_csv_adapter", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_csv_adapter_defaults_missing_optional_json_fields_to_empty_lists(
    tmp_path: Path,
) -> None:
    source = tmp_path / "goldset.csv"
    target = tmp_path / "goldset.jsonl"
    source.write_text(
        "case_id,phase,user_text,history,must,must_not\n"
        'case-1,single,hello,[],["answer"],[]\n',
        encoding="utf-8",
    )

    adapter = load_csv_adapter()
    count = adapter.csv_to_jsonl(source, target)
    converted = json.loads(target.read_text(encoding="utf-8"))

    assert count == 1
    assert converted["character_ids"] == []
    assert converted["expected_speaker_ids"] == []


def test_project_default_goldset_converts_all_cases(tmp_path: Path) -> None:
    adapter = load_csv_adapter()
    target = tmp_path / "default-goldset.jsonl"

    count = adapter.csv_to_jsonl(adapter.DEFAULT_GOLDSET, target)
    converted_cases = [
        json.loads(line)
        for line in target.read_text(encoding="utf-8").splitlines()
    ]

    assert count == 13
    assert len(converted_cases) == 13
    c_multi_008 = next(item for item in converted_cases if item["case_id"] == "C_MULTI_008")
    assert c_multi_008["setup_messages"][0]["speaker_id"] == "character_a"
    assert c_multi_008["seed_memories"] == []
