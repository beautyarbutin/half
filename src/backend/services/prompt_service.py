import json

from sqlalchemy.orm import Session

from models import Agent, Project, Task


def generate_plan_prompt(
    project: Project,
    selected_agents: list[Agent],
    plan_path: str,
    usage_path: str | None = None,
) -> str:
    selected_lines = "\n".join(
        f"- {agent.name} ({agent.slug}, {agent.agent_type}{f', {agent.model_name}' if agent.model_name else ''})"
        for agent in selected_agents
    ) or "- 未指定参与 Agent"

    return f"""你是项目 [{project.name}] 的执行 Agent。

## 任务目标
{project.goal}

## 协作约定
- 项目仓库地址：{project.git_repo_url or '未提供'}
- 协作目录：{project.collaboration_dir or '仓库根目录'}

## 本次参与规划的 Agent
{selected_lines}

请根据参与 Agent 的数量、能力特点和分工边界来拆分子任务，尽量让每个子任务的 assignee 都来自上述列表。

## 输出要求
请输出结构化工作计划，格式为 JSON，包含以下字段：
- plan_name: 计划名称
- tasks: 任务列表，每个任务包含 task_code, task_name, description, assignee, depends_on, expected_output

将计划写入 {plan_path} 文件。
完成后执行 git add、git commit、git push。"""

    if usage_path:
        prompt += f"""

额外要求：
- 请在 {usage_path} 中写入本次生成计划时的模型用量或剩余额度信息（若当前 Agent 支持提供）。"""

    return prompt


def generate_task_prompt(
    db: Session,
    project: Project,
    task: Task,
    include_usage: bool = False,
) -> str:
    # Gather predecessor output paths
    depends_on = json.loads(task.depends_on_json) if task.depends_on_json else []
    predecessor_lines = ""
    if depends_on:
        predecessors = db.query(Task).filter(
            Task.project_id == project.id,
            Task.task_code.in_(depends_on),
        ).all()
        paths = []
        for p in predecessors:
            path = p.result_file_path or f"outputs/{p.task_code}/result.json"
            paths.append(f"- {p.task_code}: {path}")
        if paths:
            predecessor_lines = "\n".join(paths)
        else:
            predecessor_lines = "无前序任务输出"
    else:
        predecessor_lines = "无前序任务输出"

    prompt = f"""你是项目 [{project.name}] 的执行 Agent。

## 任务信息
- 任务码：{task.task_code}
- 任务名称：{task.task_name}
- 任务描述：{task.description}

## 前序任务输出
{predecessor_lines}

## 输出要求
1. 将输出写入路径：outputs/{task.task_code}/result.json
2. 文件中必须包含字段 "task_code": "{task.task_code}"
3. 完成后执行 git add、git commit、git push"""

    if include_usage:
        prompt += f"""

4. 在 outputs/{task.task_code}/usage.json 中写入当前剩余用量信息"""

    return prompt
