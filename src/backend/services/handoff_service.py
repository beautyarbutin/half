import json
from dataclasses import dataclass
from typing import Any, Callable

from models import Project
from services import git_service


HANDOFF_SCHEMA_FIELDS = (
    "goal",
    "changed_files",
    "verification",
    "unfinished_items",
    "risks",
    "next_steps",
)

HANDOFF_FIELD_LABELS = {
    "goal": "本阶段目标",
    "changed_files": "前序变更",
    "verification": "验证证据",
    "unfinished_items": "未完成项",
    "risks": "风险/约束",
    "next_steps": "建议下一步",
}


@dataclass(frozen=True)
class HandoffArm:
    arm_id: str
    label: str
    description: str
    format: str
    include_fields: tuple[str, ...]


HANDOFF_ARMS: dict[str, HandoffArm] = {
    "A_full": HandoffArm(
        arm_id="A_full",
        label="完整组",
        description="注入最小 schema 的全部 6 个字段，作为基线。",
        format="structured",
        include_fields=HANDOFF_SCHEMA_FIELDS,
    ),
    "B_no_verification": HandoffArm(
        arm_id="B_no_verification",
        label="去掉验证证据",
        description="不注入 verification 字段，用于观察测试信息是否关键。",
        format="structured",
        include_fields=tuple(field for field in HANDOFF_SCHEMA_FIELDS if field != "verification"),
    ),
    "C_no_unfinished_items": HandoffArm(
        arm_id="C_no_unfinished_items",
        label="去掉未完成项",
        description="不注入 unfinished_items 字段，用于观察后续 Agent 是否更容易漏任务。",
        format="structured",
        include_fields=tuple(field for field in HANDOFF_SCHEMA_FIELDS if field != "unfinished_items"),
    ),
    "D_no_risks": HandoffArm(
        arm_id="D_no_risks",
        label="去掉风险/约束",
        description="不注入 risks 字段，用于观察是否更容易误改或破坏既有逻辑。",
        format="structured",
        include_fields=tuple(field for field in HANDOFF_SCHEMA_FIELDS if field != "risks"),
    ),
    "E_summary_only": HandoffArm(
        arm_id="E_summary_only",
        label="只给自然语言摘要",
        description="不暴露结构化字段名，只注入一段自然语言摘要。",
        format="summary",
        include_fields=HANDOFF_SCHEMA_FIELDS,
    ),
    "F_full_context": HandoffArm(
        arm_id="F_full_context",
        label="给全文上下文",
        description="注入前序 handoff.json 与 result.json 原文，用于观察过量上下文的影响。",
        format="full_context",
        include_fields=HANDOFF_SCHEMA_FIELDS,
    ),
}


def get_handoff_arm(arm_id: str | None) -> HandoffArm | None:
    value = (arm_id or "").strip()
    if not value:
        return None
    arm = HANDOFF_ARMS.get(value)
    if arm is None:
        allowed = ", ".join(HANDOFF_ARMS)
        raise ValueError(f"Invalid handoff_arm_id: {value}. Allowed: {allowed}")
    return arm


def handoff_arm_options() -> list[dict[str, object]]:
    return [
        {
            "arm_id": arm.arm_id,
            "label": arm.label,
            "description": arm.description,
            "format": arm.format,
            "include_fields": list(arm.include_fields),
        }
        for arm in HANDOFF_ARMS.values()
    ]


def predecessor_handoff_path(project: Project, task_code: str) -> str:
    base = (project.collaboration_dir or "").strip("/")
    if base:
        return f"{base}/{task_code}/handoff.json"
    return f"{task_code}/handoff.json"


def predecessor_result_path(project: Project, task_code: str) -> str:
    base = (project.collaboration_dir or "").strip("/")
    if base:
        return f"{base}/{task_code}/result.json"
    return f"{task_code}/result.json"


def load_predecessor_handoff(project: Project, task_code: str) -> str | None:
    return git_service.read_file(
        project.id,
        predecessor_handoff_path(project, task_code),
        git_repo_url=project.git_repo_url,
        prefer_remote=True,
    )


def load_predecessor_result(project: Project, task_code: str) -> str | None:
    return git_service.read_file(
        project.id,
        predecessor_result_path(project, task_code),
        git_repo_url=project.git_repo_url,
        prefer_remote=True,
    )


def render_handoff_experiment_section(
    project: Project,
    predecessor_codes: list[str],
    arm_id: str | None,
    handoff_loader: Callable[[Project, str], str | None] | None = None,
    result_loader: Callable[[Project, str], str | None] | None = None,
) -> str:
    arm = get_handoff_arm(arm_id)
    if arm is None or not predecessor_codes:
        return ""

    handoff_loader = handoff_loader or load_predecessor_handoff
    result_loader = result_loader or load_predecessor_result
    rendered_blocks = []
    missing_paths = []

    for task_code in predecessor_codes:
        raw_handoff = handoff_loader(project, task_code)
        if raw_handoff is None:
            missing_paths.append(predecessor_handoff_path(project, task_code))
            continue
        rendered_blocks.append(_render_single_handoff_block(project, task_code, raw_handoff, arm, result_loader))

    header = [
        "## Handoff 消融实验上下文",
        f"- 实验组：{arm.arm_id}（{arm.label}）",
        f"- 注入格式：{arm.format}",
        "- 最小 handoff schema：goal, changed_files, verification, unfinished_items, risks, next_steps",
        "- 你只能把本节中可见的信息当作前序 handoff；不要凭空补全被当前实验组隐藏的字段。",
        "- 如果缺少验证证据、未完成项或风险/约束，请基于可见信息完成任务，并在最终报告中说明缺失信息带来的不确定性。",
    ]
    if arm.format == "structured":
        header.append(f"- 当前实验组可见字段：{', '.join(arm.include_fields)}")
    if missing_paths:
        header.append("- 未读取到以下前序 handoff 文件：" + ", ".join(missing_paths))

    if not rendered_blocks:
        header.append("未读取到可注入的前序 handoff 内容。")
        return "\n".join(header)

    return "\n".join(header + [""] + rendered_blocks)


def render_handoff_output_contract(task_code: str) -> str:
    fields = ", ".join(HANDOFF_SCHEMA_FIELDS)
    return f"""## Handoff 产出要求（用于后续消融实验）
如果本任务完成后会被后续任务依赖，请在任务目录中同时写入 `handoff.json`，字段必须收敛为最小 schema：

```json
{{
  "goal": "本阶段目标",
  "changed_files": ["修改过的文件路径"],
  "verification": "已经运行的测试、命令和结果",
  "unfinished_items": "未完成事项",
  "risks": "风险和约束",
  "next_steps": "建议下一步"
}}
```

- 只使用这些字段，不要新增同义字段；字段缺失时用空字符串或空数组。
- `changed_files` 使用仓库根相对路径数组。
- `result.json.artifacts` 应包含本任务的 `handoff.json` 路径，便于后续任务读取。
- 本任务码为 `{task_code}`；后续实验会按字段集合 `{fields}` 做消融。"""


def _render_single_handoff_block(
    project: Project,
    task_code: str,
    raw_handoff: str,
    arm: HandoffArm,
    result_loader: Callable[[Project, str], str | None],
) -> str:
    if arm.format == "full_context":
        result = result_loader(project, task_code)
        parts = [
            f"### 前序任务 {task_code} 完整上下文",
            f"`{predecessor_handoff_path(project, task_code)}`:",
            "```json",
            raw_handoff.strip(),
            "```",
        ]
        if result is not None:
            parts.extend([
                f"`{predecessor_result_path(project, task_code)}`:",
                "```json",
                result.strip(),
                "```",
            ])
        return "\n".join(parts)

    parsed = _parse_handoff_json(raw_handoff)
    if arm.format == "summary":
        return _render_summary_handoff(task_code, parsed, raw_handoff, arm)
    return _render_structured_handoff(task_code, parsed, raw_handoff, arm)


def _parse_handoff_json(raw_handoff: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw_handoff)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _render_structured_handoff(
    task_code: str,
    parsed: dict[str, Any] | None,
    raw_handoff: str,
    arm: HandoffArm,
) -> str:
    if parsed is None:
        return "\n".join([
            f"### 前序任务 {task_code}",
            "handoff.json 不是合法 JSON 对象，按原文注入：",
            "```text",
            raw_handoff.strip(),
            "```",
        ])

    lines = [f"### 前序任务 {task_code} handoff"]
    for field in arm.include_fields:
        value = parsed.get(field)
        lines.append(f"- {HANDOFF_FIELD_LABELS[field]} (`{field}`): {_format_field_value(value)}")
    return "\n".join(lines)


def _render_summary_handoff(
    task_code: str,
    parsed: dict[str, Any] | None,
    raw_handoff: str,
    arm: HandoffArm,
) -> str:
    if parsed is None:
        summary = " ".join(raw_handoff.strip().split())
    else:
        values = [
            _format_field_value(parsed.get(field), inline=True)
            for field in arm.include_fields
            if _has_value(parsed.get(field))
        ]
        summary = "；".join(value for value in values if value)
    if not summary:
        summary = "未提供可用摘要。"
    return f"### 前序任务 {task_code} 自然语言摘要\n{summary}"


def _format_field_value(value: Any, *, inline: bool = False) -> str:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        if not items:
            return "未提供"
        return "、".join(items) if inline else ", ".join(f"`{item}`" for item in items)
    if isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = "" if value is None else str(value)
    text = " ".join(text.strip().split())
    return text or "未提供"


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, dict)):
        return bool(value)
    return bool(str(value).strip())

