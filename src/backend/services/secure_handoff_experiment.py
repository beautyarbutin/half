from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings


SCHEMA_FIELDS = (
    "goal",
    "changed_files",
    "verification",
    "unfinished_items",
    "risks",
    "next_steps",
)

FIELD_LABELS = {
    "goal": "Goal",
    "changed_files": "Predecessor changes",
    "verification": "Verification evidence",
    "unfinished_items": "Unfinished items",
    "risks": "Risks and constraints",
    "next_steps": "Recommended next steps",
}

PROBE_PREFIXES = {
    "goal": "test_goal_",
    "changed_files": "test_changed_",
    "verification": "test_verify_",
    "unfinished_items": "test_unfinished_",
    "risks": "test_risks_",
    "next_steps": "test_next_",
}


@dataclass(frozen=True)
class SecureArm:
    arm_id: str
    label: str
    include_fields: tuple[str, ...]


SECURE_ARMS: dict[str, SecureArm] = {
    "A_full": SecureArm("A_full", "Full six-field handoff", SCHEMA_FIELDS),
    "B_no_goal": SecureArm(
        "B_no_goal",
        "Without goal",
        tuple(field for field in SCHEMA_FIELDS if field != "goal"),
    ),
    "C_no_changed_files": SecureArm(
        "C_no_changed_files",
        "Without predecessor changes",
        tuple(field for field in SCHEMA_FIELDS if field != "changed_files"),
    ),
    "D_no_verification": SecureArm(
        "D_no_verification",
        "Without verification evidence",
        tuple(field for field in SCHEMA_FIELDS if field != "verification"),
    ),
    "E_no_unfinished_items": SecureArm(
        "E_no_unfinished_items",
        "Without unfinished items",
        tuple(field for field in SCHEMA_FIELDS if field != "unfinished_items"),
    ),
    "F_no_risks": SecureArm(
        "F_no_risks",
        "Without risks and constraints",
        tuple(field for field in SCHEMA_FIELDS if field != "risks"),
    ),
    "G_no_next_steps": SecureArm(
        "G_no_next_steps",
        "Without recommended next steps",
        tuple(field for field in SCHEMA_FIELDS if field != "next_steps"),
    ),
    "H_no_handoff": SecureArm("H_no_handoff", "No handoff negative control", ()),
}


def utcnow_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def secure_arm_options() -> list[dict[str, Any]]:
    return [
        {
            "arm_id": arm.arm_id,
            "label": arm.label,
            "include_fields": list(arm.include_fields),
            "omitted_fields": [field for field in SCHEMA_FIELDS if field not in arm.include_fields],
        }
        for arm in SECURE_ARMS.values()
    ]


def list_experiments() -> list[dict[str, Any]]:
    root = Path(settings.HANDOFF_EXPERIMENT_PRIVATE_ROOT).resolve()
    if not root.exists():
        return []
    experiments: list[dict[str, Any]] = []
    for manifest_path in sorted(root.glob("*/manifest.json")):
        try:
            manifest = _read_json(manifest_path)
        except (OSError, ValueError):
            continue
        experiments.append(
            {
                "experiment_id": manifest.get("experiment_id", manifest_path.parent.name),
                "max_attempts": int(manifest.get("max_attempts", 3)),
                "feedback_mode": manifest.get("feedback_mode", "probe_ids"),
            }
        )
    return experiments


def prepare_run(
    experiment_id: str,
    arm_id: str,
    *,
    model: str = "gpt-5.5",
    max_attempts: int | None = None,
) -> dict[str, Any]:
    arm = _get_arm(arm_id)
    experiment_dir, manifest = _load_manifest(experiment_id)
    canonical = _load_canonical(experiment_dir, manifest)
    canaries = _load_canaries(experiment_dir)

    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    run_dir = _runs_root() / experiment_id / arm_id / run_id
    workspace = run_dir / "workspace"
    run_dir.mkdir(parents=True, exist_ok=False)

    fixture_repo = Path(str(manifest["fixture_repo"])).expanduser().resolve()
    if not fixture_repo.is_dir():
        raise ValueError(f"Fixture repository does not exist: {fixture_repo}")
    shutil.copytree(
        fixture_repo,
        workspace,
        ignore=shutil.ignore_patterns(".git", ".venv", ".pytest_cache", "__pycache__", "*.pyc"),
    )

    baseline = _snapshot_workspace(workspace)
    prompt = _render_prompt(manifest, arm, canonical, canaries, workspace)
    attempt_limit = max_attempts or int(manifest.get("max_attempts", 3))
    if attempt_limit < 1 or attempt_limit > 10:
        raise ValueError("max_attempts must be between 1 and 10")

    record: dict[str, Any] = {
        "run_id": run_id,
        "experiment_id": experiment_id,
        "arm_id": arm.arm_id,
        "arm_label": arm.label,
        "visible_fields": list(arm.include_fields),
        "omitted_fields": [field for field in SCHEMA_FIELDS if field not in arm.include_fields],
        "model": model,
        "max_attempts": attempt_limit,
        "status": "prepared",
        "workspace": str(workspace),
        "private_run_dir": str(run_dir),
        "prompt_sha256": _sha256_text(prompt),
        "baseline": baseline,
        "attempts": [],
        "interventions": [],
        "infra_retries": [],
        "contaminated": False,
        "contamination_matches": [],
        "created_at": utcnow_text(),
        "updated_at": utcnow_text(),
    }
    _atomic_write_text(run_dir / "prompt.txt", prompt)
    _write_record(record)
    return _public_record(record)


def evaluate_run(run_id: str) -> dict[str, Any]:
    return submit_manual_attempt(run_id)


def submit_manual_attempt(
    run_id: str,
    *,
    conversation_id: str | None = None,
    usage: dict[str, int] | None = None,
    notes: str = "",
    agent_output: str = "",
) -> dict[str, Any]:
    record = load_run(run_id, private=True)
    if len(record["attempts"]) >= int(record["max_attempts"]):
        raise ValueError("This run has reached its maximum number of attempts")
    attempt_number = len(record["attempts"]) + 1
    evaluation = evaluate_workspace(record, attempt_number)
    attempt = {
        "attempt_number": attempt_number,
        "started_at": utcnow_text(),
        "completed_at": utcnow_text(),
        "session_id": conversation_id,
        "exit_code": None,
        "usage": _normalize_usage(usage),
        "feedback_received": None,
        "evaluation": evaluation,
        "code_changed": bool(evaluation["changed_files"]),
        "manual_evaluation": True,
        "notes": notes.strip(),
        "agent_output": agent_output.strip(),
    }
    record["attempts"].append(attempt)
    _apply_contamination_text(record, agent_output)
    if evaluation["resolved"]:
        record["status"] = "resolved"
    elif attempt_number >= int(record["max_attempts"]):
        record["status"] = "failed"
    else:
        record["status"] = "needs_rework"
    record["updated_at"] = utcnow_text()
    _write_record(record)
    result = _public_record(record)
    result["repair_prompt"] = None if evaluation["resolved"] else _build_feedback(attempt)
    return result


def get_run_prompt(run_id: str) -> dict[str, str]:
    record = load_run(run_id, private=True)
    prompt_path = Path(record["private_run_dir"]) / "prompt.txt"
    return {
        "run_id": run_id,
        "arm_id": record["arm_id"],
        "workspace": record["workspace"],
        "prompt": prompt_path.read_text(encoding="utf-8"),
    }


def add_intervention(
    run_id: str,
    *,
    kind: str,
    detail: str,
    minutes: float = 0,
) -> dict[str, Any]:
    record = load_run(run_id, private=True)
    event = {"kind": kind, "detail": detail.strip(), "minutes": minutes, "at": utcnow_text()}
    if kind == "infra_retry":
        record["infra_retries"].append(event)
    else:
        record["interventions"].append(event)
    record["updated_at"] = utcnow_text()
    _write_record(record)
    return _public_record(record)


def load_run(run_id: str, *, private: bool = False) -> dict[str, Any]:
    matches = list(_runs_root().glob(f"*/*/{run_id}/run.json"))
    if len(matches) != 1:
        raise ValueError(f"Experiment run not found: {run_id}")
    record = _read_json(matches[0])
    return record if private else _public_record(record)


def summarize_experiment(experiment_id: str) -> dict[str, Any]:
    root = _runs_root() / experiment_id
    rows: list[dict[str, Any]] = []
    if root.exists():
        for path in root.glob("*/*/run.json"):
            rows.append(_public_record(_read_json(path)))

    by_arm: dict[str, dict[str, Any]] = {}
    for row in rows:
        metrics = row["metrics"]
        arm = by_arm.setdefault(
            row["arm_id"],
            {
                "runs": 0,
                "prepared_runs": 0,
                "attempted_runs": 0,
                "clean_runs": 0,
                "first_attempt_resolved": 0,
                "final_resolved": 0,
                "token_total": 0,
                "rework_count": 0,
                "interaction_rounds": 0,
            },
        )
        arm["runs"] += 1
        if not row["attempts"]:
            arm["prepared_runs"] += 1
            continue
        arm["attempted_runs"] += 1
        if not row["contaminated"]:
            arm["clean_runs"] += 1
        arm["first_attempt_resolved"] += int(metrics["first_attempt_resolved"])
        arm["final_resolved"] += int(metrics["final_resolved"])
        arm["token_total"] += metrics["token_total"]
        arm["rework_count"] += metrics["rework_count"]
        arm["interaction_rounds"] += metrics["interaction_rounds"]
    return {"experiment_id": experiment_id, "runs": rows, "by_arm": by_arm}


def evaluate_workspace(record: dict[str, Any], attempt_number: int) -> dict[str, Any]:
    experiment_dir, manifest = _load_manifest(record["experiment_id"])
    workspace = Path(record["workspace"])
    run_dir = Path(record["private_run_dir"])
    evaluation_dir = run_dir / "evaluations" / f"attempt-{attempt_number}"
    evaluation_dir.mkdir(parents=True, exist_ok=True)

    changed_files = _changed_files(workspace, record["baseline"])
    forbidden = {
        "src/reservation_fixture/allocation/engine.py",
        "src/reservation_fixture/reservation/service.py",
        "src/reservation_fixture/api/serializer.py",
    }
    forbidden_touched = sorted(forbidden.intersection(changed_files))
    env = os.environ.copy()
    env["PYTHONPATH"] = str(workspace / "src")
    env["HANDOFF_FORBIDDEN_TOUCH"] = ";".join(forbidden_touched)

    public = _run_pytest(
        workspace,
        ["tests"],
        evaluation_dir / "public.xml",
        env,
    )
    hidden_path = _resolve_private_child(experiment_dir, str(manifest["hidden_tests"]))
    hidden = _run_pytest(
        workspace,
        [str(hidden_path)],
        evaluation_dir / "hidden.xml",
        env,
    )
    probe_scores = _probe_scores(hidden["cases"])
    return {
        "resolved": public["exit_code"] == 0 and hidden["exit_code"] == 0,
        "public": public,
        "hidden": hidden,
        "probe_scores": probe_scores,
        "changed_files": changed_files,
        "forbidden_files_touched": forbidden_touched,
    }


def _run_pytest(
    workspace: Path,
    targets: list[str],
    junit_path: Path,
    env: dict[str, str],
) -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", "-q", *targets, f"--junitxml={junit_path}"]
    completed = subprocess.run(
        command,
        cwd=workspace,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=300,
        check=False,
    )
    cases = _parse_junit(junit_path)
    return {
        "exit_code": completed.returncode,
        "passed": sum(case["status"] == "passed" for case in cases),
        "failed": sum(case["status"] == "failed" for case in cases),
        "total": len(cases),
        "failed_test_ids": [case["name"] for case in cases if case["status"] == "failed"],
        "cases": cases,
        "output_tail": "\n".join((completed.stdout + completed.stderr).splitlines()[-20:]),
    }


def _parse_junit(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    root = ET.parse(path).getroot()
    cases: list[dict[str, str]] = []
    for testcase in root.iter("testcase"):
        status = "passed"
        if testcase.find("failure") is not None or testcase.find("error") is not None:
            status = "failed"
        elif testcase.find("skipped") is not None:
            status = "skipped"
        cases.append(
            {
                "name": testcase.attrib.get("name", "unknown"),
                "classname": testcase.attrib.get("classname", ""),
                "status": status,
            }
        )
    return cases


def _probe_scores(cases: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    scores: dict[str, dict[str, int]] = {}
    for field, prefix in PROBE_PREFIXES.items():
        selected = [case for case in cases if case["name"].startswith(prefix)]
        scores[field] = {
            "passed": sum(case["status"] == "passed" for case in selected),
            "total": len(selected),
        }
    return scores


def _build_feedback(attempt: dict[str, Any]) -> str:
    evaluation = attempt["evaluation"]
    failed = evaluation["public"]["failed_test_ids"] + evaluation["hidden"]["failed_test_ids"]
    if not failed:
        return (
            "The evaluator could not complete successfully. Inspect the implementation and public "
            "test output, then submit a repaired attempt."
        )
    lines = [
        "The private evaluator rejected the previous attempt.",
        "Failed probe identifiers:",
        *(f"- {test_id}" for test_id in failed),
        "Repair the implementation using only the handoff already visible to you and the repository source.",
        "Do not search for hidden tests or omitted handoff fields.",
    ]
    return "\n".join(lines)


def _render_prompt(
    manifest: dict[str, Any],
    arm: SecureArm,
    canonical: dict[str, Any],
    canaries: dict[str, str],
    workspace: Path,
) -> str:
    lines = [
        "You are the successor agent in a controlled handoff ablation experiment.",
        "",
        "## Required workspace",
        "You must work in this exact source workspace:",
        f"`{workspace}`",
        "",
        "Before reading or editing files, switch to that directory and verify it contains `src/`, `tests/`, and `pyproject.toml`.",
        "If your current directory is not this exact workspace, change directories first. Do not use the conversation's default working directory.",
        "",
        "## Successor task",
        str(manifest["public_task"]).strip(),
        "",
        "## Isolation contract",
        "- Treat only the handoff view below as predecessor communication.",
        "- Do not access Git history, remote repositories, sibling runs, collaboration repositories, or evaluator files.",
        "- Do not infer or reconstruct fields omitted from this handoff view.",
        "- Work only inside the supplied source workspace.",
        "- Run the public regression tests available in the workspace before submitting.",
        "",
        f"## Handoff view: {arm.arm_id}",
    ]
    if not arm.include_fields:
        lines.append("No predecessor handoff fields are visible in this run.")
    for field in arm.include_fields:
        value = canonical[field]
        trace = canaries.get(field, "")
        lines.append(f"### {FIELD_LABELS[field]} (`{field}`) [{trace}]")
        if isinstance(value, list):
            lines.extend(f"- `{item}`" for item in value)
        else:
            lines.append(str(value))
    lines.extend(
        [
            "",
            "## Submission",
            "Implement the successor work in the supplied workspace. Do not create handoff or result files.",
            "HALF will capture the workspace diff and run private evaluation after you stop.",
        ]
    )
    return "\n".join(lines)


def _load_manifest(experiment_id: str) -> tuple[Path, dict[str, Any]]:
    if not experiment_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in experiment_id):
        raise ValueError("Invalid experiment_id")
    experiment_dir = (_private_root() / experiment_id).resolve()
    if _private_root() not in experiment_dir.parents:
        raise ValueError("Experiment path escapes private root")
    manifest_path = experiment_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Experiment manifest not found: {experiment_id}")
    manifest = _read_json(manifest_path)
    if manifest.get("experiment_id") != experiment_id:
        raise ValueError("Manifest experiment_id does not match directory")
    for required in ("fixture_repo", "public_task", "canonical_handoff", "hidden_tests"):
        if not manifest.get(required):
            raise ValueError(f"Manifest missing required field: {required}")
    return experiment_dir, manifest


def _load_canonical(experiment_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    canonical = _read_json(_resolve_private_child(experiment_dir, str(manifest["canonical_handoff"])))
    if set(canonical) != set(SCHEMA_FIELDS):
        raise ValueError(f"Canonical handoff must contain exactly: {', '.join(SCHEMA_FIELDS)}")
    if not isinstance(canonical["changed_files"], list):
        raise ValueError("changed_files must be an array")
    return canonical


def _load_canaries(experiment_dir: Path) -> dict[str, str]:
    path = experiment_dir / "canaries.json"
    if not path.exists():
        return {}
    value = _read_json(path)
    return {str(key): str(item) for key, item in value.items() if key in SCHEMA_FIELDS}


def _apply_contamination_text(record: dict[str, Any], text: str) -> None:
    experiment_dir, _ = _load_manifest(record["experiment_id"])
    canaries = _load_canaries(experiment_dir)
    matches = [
        canaries[field]
        for field in record["omitted_fields"]
        if canaries.get(field) and canaries[field] in text
    ]
    if matches:
        record["contaminated"] = True
        record["contamination_matches"] = sorted(set(record["contamination_matches"] + matches))


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    attempts = record.get("attempts", [])
    token_total = sum(int(attempt.get("usage", {}).get("total_tokens", 0)) for attempt in attempts)
    first_resolved = bool(attempts and attempts[0]["evaluation"]["resolved"])
    final_resolved = record.get("status") == "resolved"
    return {
        "run_id": record["run_id"],
        "experiment_id": record["experiment_id"],
        "arm_id": record["arm_id"],
        "arm_label": record["arm_label"],
        "visible_fields": record["visible_fields"],
        "omitted_fields": record["omitted_fields"],
        "model": record["model"],
        "status": record["status"],
        "workspace": record["workspace"],
        "attempts": attempts,
        "contaminated": record.get("contaminated", False),
        "contamination_matches": record.get("contamination_matches", []),
        "interventions": record.get("interventions", []),
        "infra_retries": record.get("infra_retries", []),
        "metrics": {
            "first_attempt_resolved": first_resolved,
            "final_resolved": final_resolved,
            "interaction_rounds": len(attempts),
            "rework_count": max(0, len(attempts) - 1),
            "human_intervention_count": len(record.get("interventions", [])),
            "human_intervention_minutes": sum(
                float(event.get("minutes", 0)) for event in record.get("interventions", [])
            ),
            "infra_retry_count": len(record.get("infra_retries", [])),
            "token_total": token_total,
        },
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
    }


def _snapshot_workspace(workspace: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in workspace.rglob("*"):
        if path.is_file() and not _ignored_workspace_path(path.relative_to(workspace)):
            result[path.relative_to(workspace).as_posix()] = _sha256_bytes(path.read_bytes())
    return result


def _changed_files(workspace: Path, baseline: dict[str, str]) -> list[str]:
    current = _snapshot_workspace(workspace)
    return sorted(path for path in set(baseline) | set(current) if baseline.get(path) != current.get(path))


def _ignored_workspace_path(path: Path) -> bool:
    return any(part in {".git", ".pytest_cache", "__pycache__", ".venv"} for part in path.parts) or path.suffix == ".pyc"


def _empty_usage() -> dict[str, int]:
    return {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
    }


def _normalize_usage(usage: dict[str, int] | None) -> dict[str, int]:
    if usage is None:
        return _empty_usage()
    normalized = _empty_usage()
    for key in normalized:
        value = int(usage.get(key, 0) or 0)
        if value < 0:
            raise ValueError(f"Usage value cannot be negative: {key}")
        normalized[key] = value
    if not normalized["total_tokens"]:
        normalized["total_tokens"] = normalized["input_tokens"] + normalized["output_tokens"]
    return normalized


def _get_arm(arm_id: str) -> SecureArm:
    try:
        return SECURE_ARMS[arm_id]
    except KeyError as exc:
        raise ValueError(f"Unknown secure handoff arm: {arm_id}") from exc


def _private_root() -> Path:
    return Path(settings.HANDOFF_EXPERIMENT_PRIVATE_ROOT).expanduser().resolve()


def _runs_root() -> Path:
    root = Path(settings.HANDOFF_EXPERIMENT_RUNS_ROOT).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_private_child(parent: Path, relative: str) -> Path:
    path = (parent / relative).resolve()
    if parent != path and parent not in path.parents:
        raise ValueError("Private experiment path escapes its experiment directory")
    return path


def _write_record(record: dict[str, Any]) -> None:
    run_dir = Path(record["private_run_dir"])
    _atomic_write_text(run_dir / "run.json", json.dumps(record, ensure_ascii=False, indent=2))


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
