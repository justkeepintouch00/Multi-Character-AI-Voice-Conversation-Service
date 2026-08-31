from __future__ import annotations

import os
from enum import Enum

from app.memory import rule_v1, rule_v2


class MemoryPolicyVersion(str, Enum):
    V1 = "v1"
    V2 = "v2"


def get_memory_policy_version() -> MemoryPolicyVersion:
    """Return the active memory policy; invalid values fail closed to v1."""

    raw = os.getenv("MEMORY_POLICY_VERSION", MemoryPolicyVersion.V1).strip().lower()
    try:
        return MemoryPolicyVersion(raw)
    except ValueError:
        return MemoryPolicyVersion.V1


def default_memory_kind(version: MemoryPolicyVersion) -> str:
    """Return the fallback kind when the extractor omits a type."""

    return (rule_v1 if version is MemoryPolicyVersion.V1 else rule_v2).DEFAULT_MEMORY_KIND


def working_message_limit(version: MemoryPolicyVersion) -> int:
    """Return the working-memory window for the selected policy."""

    return (rule_v1 if version is MemoryPolicyVersion.V1 else rule_v2).WORKING_MESSAGE_LIMIT