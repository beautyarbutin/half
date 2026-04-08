from __future__ import annotations

from datetime import datetime
from typing import Any


def _parse_datetime(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return None


def _normalize_limit(item: dict[str, Any]) -> dict[str, Any] | None:
    limit_value = item.get("limit")
    used_value = item.get("used")
    if limit_value is None and item.get("max") is not None:
        limit_value = item.get("max")
    if used_value is None and item.get("current") is not None:
        used_value = item.get("current")

    remaining_value = item.get("remaining")
    if remaining_value is None and isinstance(limit_value, (int, float)) and isinstance(used_value, (int, float)):
        remaining_value = limit_value - used_value

    period = item.get("period") or item.get("window") or item.get("limit_period") or item.get("type")
    metric = item.get("metric") or item.get("unit") or item.get("limit_metric") or "usage"
    scope = item.get("scope") or item.get("model") or item.get("model_scope")
    reset_at = _parse_datetime(item.get("reset_at") or item.get("resets_at") or item.get("reset"))

    if period is None and limit_value is None and used_value is None and remaining_value is None:
        return None

    return {
        "period": period or "custom",
        "metric": metric,
        "scope": scope,
        "limit": limit_value,
        "used": used_value,
        "remaining": remaining_value,
        "reset_at": reset_at,
    }


def extract_usage_limits(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []

    if isinstance(payload.get("limits"), list):
        return [
            normalized
            for item in payload["limits"]
            if isinstance(item, dict)
            for normalized in [_normalize_limit(item)]
            if normalized
        ]

    limits: list[dict[str, Any]] = []
    known_sections = {
        "hourly": "hourly",
        "weekly": "weekly",
        "weekly_limit": "weekly",
        "hours": "hours",
        "five_hour": "rolling_5h",
        "rolling_5h": "rolling_5h",
    }

    for key, period in known_sections.items():
        section = payload.get(key)
        if isinstance(section, dict):
            normalized = _normalize_limit({"period": period, **section})
            if normalized:
                limits.append(normalized)

    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        if {"limit", "used", "remaining", "reset_at", "max", "current"} & set(value.keys()):
            normalized = _normalize_limit({"scope": key, **value})
            if normalized:
                limits.append(normalized)

    return limits
