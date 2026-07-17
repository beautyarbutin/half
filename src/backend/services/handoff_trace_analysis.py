from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable


READ_PATTERNS = (
    r"\bget-content\b",
    r"\btype\s+",
    r"\bcat\s+",
    r"\bsed\s+",
    r"\bhead\s+",
    r"\btail\s+",
)
SEARCH_PATTERNS = (
    r"\brg\b",
    r"\bselect-string\b",
    r"\bfindstr\b",
    r"\bgrep\b",
)
TEST_PATTERNS = (
    r"\bpytest\b",
    r"\bpython\s+-m\s+pytest\b",
    r"\bnpm\s+(?:run\s+)?test\b",
    r"\bpnpm\s+(?:run\s+)?test\b",
    r"\byarn\s+test\b",
)
ROLLBACK_PATTERNS = (
    r"\bgit\s+restore\b",
    r"\bgit\s+checkout\s+--\b",
    r"\bgit\s+revert\b",
    r"\bgit\s+reset\b",
)
EDIT_TOOL_NAMES = {
    "apply_patch",
    "write_file",
    "edit_file",
    "create_file",
    "str_replace",
}
FILE_PATTERN = re.compile(
    r"(?P<path>(?:[A-Za-z]:[\\/])?[^\s\"'`|<>]+\.(?:py|js|jsx|ts|tsx|json|toml|yaml|yml|md))",
    re.IGNORECASE,
)


def acquire_codex_trace(
    conversation_id: str | None,
    manual_trace: str = "",
    *,
    previous_cursor: int = 0,
    manual_complete: bool = False,
) -> dict[str, Any]:
    """Return the new trace segment for one attempt without requiring a runner wrapper."""
    if manual_trace.strip():
        rows = manual_trace.splitlines()
        return {
            "source": "manual",
            "source_path": None,
            "complete": bool(manual_complete),
            "cursor_start": 0,
            "cursor_end": len(rows),
            "text": manual_trace,
            "reason": None if manual_complete else "manual trace was not marked complete",
        }

    if not conversation_id:
        return _missing_trace("conversation ID and manual trace are both missing")

    paths = _codex_session_paths(conversation_id)
    if len(paths) != 1:
        reason = "Codex session JSONL was not found"
        if len(paths) > 1:
            reason = "multiple Codex session JSONL files matched the conversation ID"
        return _missing_trace(reason)

    path = paths[0]
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = min(max(previous_cursor, 0), len(lines))
    segment = lines[start:]
    complete = any(_is_task_complete(line) for line in segment)
    return {
        "source": "codex_session_jsonl",
        "source_path": str(path),
        "complete": complete,
        "cursor_start": start,
        "cursor_end": len(lines),
        "text": "\n".join(segment),
        "reason": None if complete else "trace segment has no task_complete event",
    }


def extract_codex_usage(trace_text: str) -> dict[str, int] | None:
    """Return the latest cumulative usage snapshot from a Codex session trace."""
    latest: dict[str, int] | None = None
    for raw_line in trace_text.splitlines():
        row = _json_object(raw_line)
        payload = row.get("payload", {})
        if payload.get("type") != "token_count":
            continue
        usage = payload.get("info", {}).get("total_token_usage", {})
        if not isinstance(usage, dict):
            continue
        try:
            candidate = {
                "input_tokens": int(usage.get("input_tokens", 0) or 0),
                "cached_input_tokens": int(usage.get("cached_input_tokens", 0) or 0),
                "output_tokens": int(usage.get("output_tokens", 0) or 0),
                "reasoning_tokens": int(usage.get("reasoning_output_tokens", 0) or 0),
                "total_tokens": int(usage.get("total_tokens", 0) or 0),
            }
        except (TypeError, ValueError):
            continue
        if candidate["total_tokens"] > 0:
            latest = candidate
    return latest


def analyze_trace(
    trace_text: str,
    *,
    previous_searches: Iterable[str] = (),
    previous_failed_test_ids: Iterable[str] = (),
    previous_changed_files: Iterable[str] = (),
    current_hidden_passed: int = 0,
    previous_hidden_passed: int | None = None,
) -> dict[str, Any]:
    seen_searches = set(previous_searches)
    searches_for_run = set(seen_searches)
    unique_files: set[str] = set()
    evidence: list[dict[str, Any]] = []
    counts = {
        "file_read_events": 0,
        "unique_files_read": 0,
        "search_events": 0,
        "repeated_search_events": 0,
        "test_runs": 0,
        "edit_events": 0,
        "interface_guess_events": 0,
        "rollback_events": 0,
        "ineffective_edit_attempts": 0,
        "pre_edit_discovery_events": 0,
    }
    first_edit_seen = False

    for line_number, raw_line in enumerate(trace_text.splitlines(), start=1):
        row = _json_object(raw_line)
        calls = _tool_calls(row)
        if not calls:
            continue
        for call_index, (tool_name, arguments) in enumerate(calls, start=1):
            searchable = f"{tool_name} {arguments}".lower()
            categories: list[str] = []
            paths = _extract_paths(arguments)

            if _matches_any(searchable, SEARCH_PATTERNS):
                counts["search_events"] += 1
                signature = _normalize_search(searchable)
                if signature in searches_for_run:
                    counts["repeated_search_events"] += 1
                    categories.append("repeated_search")
                searches_for_run.add(signature)
                categories.append("search")
                if not first_edit_seen:
                    counts["pre_edit_discovery_events"] += 1

            if _is_read_call(tool_name, searchable):
                counts["file_read_events"] += 1
                unique_files.update(paths)
                categories.append("file_read")
                if not first_edit_seen:
                    counts["pre_edit_discovery_events"] += 1

            if _matches_any(searchable, TEST_PATTERNS):
                counts["test_runs"] += 1
                categories.append("test_run")

            if _is_edit_call(tool_name, searchable):
                counts["edit_events"] += 1
                categories.append("edit")
                first_edit_seen = True
                if previous_failed_test_ids and _overlaps_previous_files(paths, previous_changed_files):
                    counts["interface_guess_events"] += 1
                    categories.append("interface_guess")

            if _matches_any(searchable, ROLLBACK_PATTERNS):
                counts["rollback_events"] += 1
                categories.append("rollback")

            if categories:
                evidence.append(
                    {
                        "line": line_number,
                        "call_index": call_index,
                        "tool": tool_name,
                        "categories": categories,
                        "paths": sorted(paths),
                        "summary": _compact(arguments),
                    }
                )

    counts["unique_files_read"] = len(unique_files)
    if (
        previous_hidden_passed is not None
        and counts["edit_events"] > 0
        and current_hidden_passed <= previous_hidden_passed
    ):
        counts["ineffective_edit_attempts"] = 1

    return {
        "definitions_version": 1,
        "counts": counts,
        "search_signatures": sorted(searches_for_run),
        "evidence": evidence,
    }


def build_leakage_audit(
    *,
    trace_complete: bool,
    omitted_fields: Iterable[str],
    canonical_handoff: dict[str, Any],
    canaries: dict[str, str],
    visible_documents: dict[str, str],
    trace_reason: str | None = None,
) -> dict[str, Any]:
    omitted = list(omitted_fields)
    matches: list[dict[str, str]] = []
    for source, text in visible_documents.items():
        normalized_text = _normalize_text(text)
        for field in omitted:
            canary = canaries.get(field, "").strip()
            if canary and canary.lower() in text.lower():
                matches.append({"field": field, "source": source, "kind": "canary", "value": canary})
            for signature in _content_signatures(canonical_handoff.get(field)):
                if signature in normalized_text:
                    matches.append(
                        {"field": field, "source": source, "kind": "content", "value": signature}
                    )

    deduped = list({json.dumps(item, sort_keys=True): item for item in matches}.values())
    if not trace_complete:
        status = "unknown"
    elif deduped:
        status = "failed"
    else:
        status = "passed"
    return {
        "audit_version": 1,
        "status": status,
        "trace_complete": trace_complete,
        "trace_reason": trace_reason,
        "omitted_fields": omitted,
        "match_count": len(deduped),
        "matches": deduped,
        "scanned_sources": sorted(visible_documents),
        "methods": ["field_canary_exact", "normalized_distinctive_content"],
    }


def aggregate_event_tables(attempts: Iterable[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, int] = {}
    attempt_rows: list[dict[str, Any]] = []
    unique_files_read: set[str] = set()
    for attempt in attempts:
        table = attempt.get("event_table", {})
        counts = table.get("counts", {})
        attempt_rows.append(
            {"attempt_number": attempt.get("attempt_number"), "counts": counts}
        )
        for key, value in counts.items():
            totals[key] = totals.get(key, 0) + int(value)
        for item in table.get("evidence", []):
            if "file_read" in item.get("categories", []):
                unique_files_read.update(item.get("paths", []))
    totals["unique_files_read"] = len(unique_files_read)
    return {"definitions_version": 1, "totals": totals, "attempts": attempt_rows}


def _codex_session_paths(conversation_id: str) -> list[Path]:
    if not re.fullmatch(r"[A-Za-z0-9-]+", conversation_id):
        return []
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    matches: list[Path] = []
    sessions = codex_home / "sessions"
    if sessions.exists():
        matches.extend(sessions.rglob(f"*{conversation_id}*.jsonl"))
    archived = codex_home / "archived_sessions"
    if archived.exists():
        matches.extend(archived.glob(f"*{conversation_id}*.jsonl"))
    return sorted(set(path.resolve() for path in matches))


def _missing_trace(reason: str) -> dict[str, Any]:
    return {
        "source": "missing",
        "source_path": None,
        "complete": False,
        "cursor_start": 0,
        "cursor_end": 0,
        "text": "",
        "reason": reason,
    }


def _is_task_complete(line: str) -> bool:
    row = _json_object(line)
    return bool(
        row.get("type") == "event_msg"
        and isinstance(row.get("payload"), dict)
        and row["payload"].get("type") == "task_complete"
    )


def _json_object(line: str) -> dict[str, Any]:
    try:
        value = json.loads(line)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _tool_calls(row: dict[str, Any]) -> list[tuple[str, str]]:
    if row.get("type") != "response_item" or not isinstance(row.get("payload"), dict):
        return []
    payload = row["payload"]
    if payload.get("type") not in {"function_call", "custom_tool_call"}:
        return []
    name = str(payload.get("name", payload.get("tool_name", "unknown")))
    arguments = payload.get("arguments", payload.get("input", ""))
    if not isinstance(arguments, str):
        arguments = json.dumps(arguments, ensure_ascii=False)
    if name in {"functions.exec", "exec"}:
        try:
            wrapper = json.loads(arguments)
        except json.JSONDecodeError:
            wrapper = {}
        source = str(wrapper.get("code", wrapper.get("source", arguments)))
        matches = list(re.finditer(r"tools\.([A-Za-z0-9_]+)\s*\(", source))
        if matches:
            return [
                (
                    match.group(1),
                    source[match.start() : matches[index + 1].start()]
                    if index + 1 < len(matches)
                    else source[match.start() :],
                )
                for index, match in enumerate(matches)
            ]
    return [(name, arguments)]


def _is_read_call(tool_name: str, text: str) -> bool:
    lowered = tool_name.lower()
    if lowered in {"read_file", "view_file", "read_mcp_resource"}:
        return True
    return _matches_any(text, READ_PATTERNS)


def _is_edit_call(tool_name: str, text: str) -> bool:
    lowered = tool_name.lower()
    if lowered in EDIT_TOOL_NAMES or "apply_patch" in lowered:
        return True
    return bool(re.search(r"\bset-content\b|\badd-content\b", text))


def _extract_paths(arguments: str) -> set[str]:
    return {match.group("path").replace("\\", "/") for match in FILE_PATTERN.finditer(arguments)}


def _overlaps_previous_files(paths: set[str], previous_files: Iterable[str]) -> bool:
    normalized = {path.replace("\\", "/").lower() for path in previous_files}
    return any(any(path.lower().endswith(old) for old in normalized) for path in paths)


def _matches_any(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _normalize_search(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _normalize_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9_.:-]+", value.lower()))


def _content_signatures(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    words = re.findall(r"[a-z0-9_.:-]+", value.lower())
    if len(words) < 8:
        return []
    signatures = []
    for index in range(0, len(words) - 7, 8):
        signature = " ".join(words[index : index + 8])
        if len(signature) >= 48:
            signatures.append(signature)
    return signatures


def _compact(value: str, limit: int = 240) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."
