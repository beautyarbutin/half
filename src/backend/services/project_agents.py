import json
from typing import Any, Optional


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def normalize_agent_assignments(value: Any) -> list[dict[str, int | bool]]:
    if not isinstance(value, list):
        return []
    assignments: list[dict[str, int | bool]] = []
    seen: set[int] = set()
    for item in value:
        if isinstance(item, int):
            agent_id = item
            co_located = False
        elif isinstance(item, dict):
            try:
                agent_id = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            co_located = _coerce_bool(item.get("co_located", False))
        else:
            continue
        if agent_id in seen:
            continue
        seen.add(agent_id)
        assignments.append({"id": agent_id, "co_located": co_located})
    return assignments


def parse_agent_assignments_json(value: Optional[str]) -> list[dict[str, int | bool]]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return normalize_agent_assignments(parsed)


def agent_ids_from_assignments_json(value: Optional[str]) -> list[int]:
    return [int(item["id"]) for item in parse_agent_assignments_json(value)]


def serialize_agent_assignments(assignments: list[dict[str, int | bool]]) -> str:
    return json.dumps(normalize_agent_assignments(assignments), ensure_ascii=False)
