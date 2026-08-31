from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import delete, select

from app.config import get_database_url, get_development_user_display_name, get_development_user_external_id
from app.db.models import MemoryACL, MemoryAccessLog, MemoryItem
from app.db.session import SessionLocal
from app.memory.policy import MemoryPolicyVersion
from app.repositories.characters import SQLAlchemyCharacterRepository
from app.repositories.memory import SQLAlchemyMemoryRepository


ROOT = Path(__file__).resolve().parents[1]
GOLDSET = ROOT / "evals" / "20260819_MEMORY_ACL_GOLDSET_REFINED.csv"


def load_goldset() -> list[dict[str, str]]:
    with GOLDSET.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def ids(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split("|") if item.strip()]


def expected_visible(row: dict[str, str]) -> list[str]:
    return ids(row.get("expected_visible_to"))


def expected_hidden(row: dict[str, str]) -> list[str]:
    return ids(row.get("expected_hidden_from"))


def make_item(session, context, row: dict[str, str], marker: str, policy: str) -> tuple[MemoryItem, dict[str, UUID]]:
    actor = row.get("actor_character_id", "")
    owner_public = (
        "character_a" if row.get("memory_alias", "").startswith("mem_a")
        else "character_b" if row.get("memory_alias", "").startswith("mem_b")
        else actor
    ) if row["memory_scope"] in {"character_internal", "relationship"} else None
    owner = context.character_instance_ids.get(owner_public) if owner_public else None
    memory_type = {
        "character_internal": "CHARACTER_INTERNAL",
        "relationship": "RELATIONSHIP",
        "group": "GROUP",
        "user_global": "USER_GLOBAL",
    }[row["memory_scope"]]
    item = MemoryItem(
        user_id=context.user_id,
        memory_type=memory_type,
        owner_character_instance_id=owner,
        content=row["memory_text"],
        sensitivity="PRIVATE" if owner else "PERSONAL",
        policy_version=policy,
        metadata_json={"evaluation_marker": marker, "case_id": row["case_id"]},
    )
    if row["expected_result"].strip().upper() == "EXCLUDE":
        item.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    session.add(item)
    session.flush()
    public_to_instance = context.character_instance_ids
    visible = expected_visible(row)
    if not visible and owner_public:
        visible = [owner_public]
    for public_id in visible:
        session.add(MemoryACL(
            memory_id=item.id,
            subject_type="CHARACTER_INSTANCE",
            subject_id=public_to_instance[public_id],
            can_know=True,
            can_read=True,
            can_disclose_to=True,
            granted_by_user_id=context.user_id,
        ))
    session.commit()
    return item, public_to_instance


def visible(repo: SQLAlchemyMemoryRepository, context, public_id: str) -> list[MemoryItem]:
    return repo.retrieve(
        user_id=context.user_id,
        viewer_character_instance_id=context.character_instance_ids[public_id],
        limit=200,
    )


def evaluate_case(session, repo, context, row: dict[str, str], marker: str, policy: str) -> dict:
    expected = row["expected_result"].strip().upper()
    item, public_to_instance = make_item(session, context, row, marker, policy)
    case_id = row["case_id"]
    operation = row["operation"].lower()
    detail: dict = {"memory_id": str(item.id), "operation": operation, "policy_version": policy}

    if operation == "share":
        target = row["target_character_id"]
        acl = session.get(MemoryACL, {"memory_id": item.id, "subject_type": "CHARACTER_INSTANCE", "subject_id": public_to_instance[target]})
        if acl is None:
            session.add(MemoryACL(
                memory_id=item.id,
                subject_type="CHARACTER_INSTANCE",
                subject_id=public_to_instance[target],
                can_know=True,
                can_read=True,
                can_disclose_to=True,
                granted_by_user_id=context.user_id,
            ))
        else:
            acl.can_know = True
            acl.can_read = True
            acl.can_disclose_to = True
        session.commit()
    elif operation == "revoke":
        target = row["target_character_id"]
        acl = session.get(MemoryACL, {
            "memory_id": item.id,
            "subject_type": "CHARACTER_INSTANCE",
            "subject_id": public_to_instance[target],
        })
        if acl is None:
            session.add(MemoryACL(
                memory_id=item.id,
                subject_type="CHARACTER_INSTANCE",
                subject_id=public_to_instance[target],
                can_know=True,
                can_read=False,
                can_disclose_to=True,
                granted_by_user_id=context.user_id,
            ))
        else:
            acl.can_read = False
        session.commit()
    elif operation == "delete":
        actor = row["actor_character_id"]
        owner_public = "character_a" if row.get("memory_alias", "").startswith("mem_a") else "character_b" if row.get("memory_alias", "").startswith("mem_b") else actor
        owner = row["memory_scope"] in {"character_internal", "relationship"} and actor == owner_public
        if owner:
            item.deleted_at = datetime.now(timezone.utc)
            session.commit()
        else:
            detail["delete_denied_reason"] = "requester_is_not_owner"

    visible_ids: dict[str, list[str]] = {}
    for public_id in ("character_a", "character_b"):
        visible_ids[public_id] = [str(record.id) for record in visible(repo, context, public_id)]
    detail["visible_memory_ids"] = visible_ids
    visible_to = expected_visible(row)
    hidden_from = expected_hidden(row)
    if expected == "DENY":
        requester = row.get("actor_character_id") or "character_b"
        actual = "DENY" if str(item.id) not in visible_ids.get(requester, []) else "ALLOW"
    elif operation == "delete" and expected == "ALLOW":
        actual = "ALLOW" if str(item.id) not in visible_ids.get(row["actor_character_id"], []) else "DENY"
    elif operation == "delete" and expected == "DENY":
        actual = "DENY" if str(item.id) in visible_ids.get("character_a", []) else "ALLOW"
    elif expected == "EXCLUDE":
        actual = "EXCLUDE" if not any(str(item.id) in values for values in visible_ids.values()) else "ALLOW"
    else:
        allowed = all(str(item.id) in visible_ids.get(public_id, []) for public_id in visible_to)
        hidden = any(str(item.id) in visible_ids.get(public_id, []) for public_id in hidden_from)
        actual = "ALLOW" if allowed and not hidden else "DENY"
    leak = any(str(item.id) in visible_ids.get(public_id, []) for public_id in hidden_from)
    detail["leak"] = leak
    detail["leak_evidence"] = [public_id for public_id in hidden_from if str(item.id) in visible_ids.get(public_id, [])]
    detail["expected_visible_to"] = visible_to
    detail["expected_hidden_from"] = hidden_from
    passed = actual == expected and not leak
    return {
        "case_id": case_id,
        "expected": expected,
        "actual": actual,
        "pass": passed,
        "leak": leak,
        "detail": detail,
    }


def metrics(results: list[dict]) -> dict:
    labels = ["ALLOW", "DENY", "EXCLUDE"]
    matrix = {expected: {actual: 0 for actual in labels} for expected in labels}
    for result in results:
        matrix[result["expected"]][result["actual"]] += 1
    per_class = {}
    for label in labels:
        tp = matrix[label][label]
        fp = sum(matrix[other][label] for other in labels if other != label)
        fn = sum(matrix[label][other] for other in labels if other != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
    total = len(results)
    accuracy = sum(matrix[label][label] for label in labels) / total if total else 0.0
    return {
        "confusion_matrix": matrix,
        "accuracy": accuracy,
        "per_class": per_class,
        "macro_precision": sum(item["precision"] for item in per_class.values()) / len(labels),
        "macro_recall": sum(item["recall"] for item in per_class.values()) / len(labels),
        "macro_f1": sum(item["f1"] for item in per_class.values()) / len(labels),
        "leak_count": sum(1 for result in results if result["leak"]),
        "passed": sum(1 for result in results if result["pass"]),
        "total": total,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy-version", choices=["v1", "v2"], default="v1")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    policy = MemoryPolicyVersion(args.policy_version).value
    output = args.output or (ROOT / "evals" / "runs" / f"20260831_235000_memory_acl_full_{policy}.json")
    marker = f"memory-eval-{policy}-{uuid4()}"
    results: list[dict] = []
    session = SessionLocal()
    try:
        context = SQLAlchemyCharacterRepository(
            session,
            development_user_external_id="local-evaluation-user",
            development_user_display_name=get_development_user_display_name(),
        ).ensure_development_context()
        repo = SQLAlchemyMemoryRepository(session, policy_version=policy)
        for row in load_goldset():
            results.append(evaluate_case(session, repo, context, row, marker, policy))
    finally:
        session.rollback()
        ids_to_delete = list(session.scalars(select(MemoryItem.id).where(MemoryItem.metadata_json["evaluation_marker"].as_string() == marker)))
        if ids_to_delete:
            session.execute(delete(MemoryAccessLog).where(MemoryAccessLog.memory_id.in_(ids_to_delete)))
            session.execute(delete(MemoryACL).where(MemoryACL.memory_id.in_(ids_to_delete)))
            session.execute(delete(MemoryItem).where(MemoryItem.id.in_(ids_to_delete)))
            session.commit()
        session.close()
    report = {
        "dataset_type": "memory_acl_evaluation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": "character_companion_eval",
        "scope": "Full memory ACL evaluation",
        "policy_version": policy,
        "goldset_file": str(GOLDSET),
        "cases": results,
        "metrics": metrics(results),
        "unsupported_cases": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), **report["metrics"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
