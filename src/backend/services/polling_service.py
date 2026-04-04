import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from database import SessionLocal
from models import Agent, Project, ProjectPlan, Task, TaskEvent
from services import git_service

logger = logging.getLogger("half.poller")


def _plan_source_path(project: Project, plan: ProjectPlan) -> str:
    if plan.source_path:
        return plan.source_path
    if project.collaboration_dir:
        return f"{project.collaboration_dir.rstrip('/')}/plan.json"
    return "plan.json"


def poll_project(db: Session, project: Project) -> None:
    if not project.git_repo_url:
        return

    try:
        git_service.ensure_repo(project.id, project.git_repo_url)
    except Exception as e:
        logger.error(f"Git pull failed for project {project.id}: {e}")
        return

    running_tasks = db.query(Task).filter(
        Task.project_id == project.id,
        Task.status == "running",
    ).all()

    now = datetime.now(timezone.utc)

    running_plans = db.query(ProjectPlan).filter(
        ProjectPlan.project_id == project.id,
        ProjectPlan.status == "running",
    ).all()

    for plan in running_plans:
        source_path = _plan_source_path(project, plan)
        plan_data = git_service.read_json(project.id, source_path)

        if isinstance(plan_data, dict) and isinstance(plan_data.get("tasks"), list) and plan_data.get("tasks"):
            plan.plan_json = json.dumps(plan_data, ensure_ascii=False, indent=2)
            plan.status = "completed"
            plan.detected_at = now
            plan.last_error = None
            plan.source_path = source_path
            plan.updated_at = now
        elif plan.dispatched_at:
            elapsed_minutes = (now - plan.dispatched_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
            if elapsed_minutes > 30:
                plan.status = "needs_attention"
                plan.last_error = f"Plan JSON not found at {source_path} after {elapsed_minutes:.1f} minutes"
                plan.updated_at = now

    for task in running_tasks:
        result_path = f"outputs/{task.task_code}/result.json"
        result_data = git_service.read_json(project.id, result_path)

        if result_data and result_data.get("task_code") == task.task_code:
            task.status = "completed"
            task.completed_at = now
            task.result_file_path = result_path
            task.updated_at = now
            db.add(TaskEvent(
                task_id=task.id,
                event_type="completed",
                detail=f"Result detected at {result_path}",
            ))
        elif task.dispatched_at:
            elapsed_minutes = (now - task.dispatched_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
            if elapsed_minutes > (task.timeout_minutes or 10):
                task.status = "needs_attention"
                task.updated_at = now
                db.add(TaskEvent(
                    task_id=task.id,
                    event_type="timeout",
                    detail=f"Timeout after {elapsed_minutes:.1f} minutes",
                ))

        # Check usage.json
        usage_path = f"outputs/{task.task_code}/usage.json"
        if git_service.file_exists(project.id, usage_path):
            task.usage_file_path = usage_path
            if task.assignee_agent_id:
                agent = db.query(Agent).filter(Agent.id == task.assignee_agent_id).first()
                if agent:
                    agent.last_usage_update_at = now
                    agent.updated_at = now

    # Check if all tasks in executing project are completed
    if project.status == "executing":
        all_tasks = db.query(Task).filter(Task.project_id == project.id).all()
        if all_tasks and all(t.status == "completed" for t in all_tasks):
            project.status = "completed"
            project.updated_at = now
    elif project.status == "planning":
        if any(plan.status in ("completed", "final") for plan in db.query(ProjectPlan).filter(ProjectPlan.project_id == project.id).all()):
            project.updated_at = now

    db.commit()


async def polling_loop(interval_seconds: int) -> None:
    logger.info(f"Polling loop started, interval={interval_seconds}s")
    while True:
        try:
            db = SessionLocal()
            try:
                projects = db.query(Project).filter(Project.status.in_(("planning", "executing"))).all()
                for project in projects:
                    try:
                        poll_project(db, project)
                    except Exception as e:
                        logger.error(f"Error polling project {project.id}: {e}")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Polling loop error: {e}")
        await asyncio.sleep(interval_seconds)
