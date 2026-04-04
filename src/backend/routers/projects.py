import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Agent, Project, ProjectPlan, Task, TaskEvent, User
from auth import get_current_user

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    goal: Optional[str] = None
    git_repo_url: Optional[str] = None
    collaboration_dir: Optional[str] = None
    agent_ids: list[int] = []


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    goal: Optional[str] = None
    git_repo_url: Optional[str] = None
    collaboration_dir: Optional[str] = None
    status: Optional[str] = None
    agent_ids: Optional[list[int]] = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    goal: Optional[str]
    git_repo_url: Optional[str]
    collaboration_dir: Optional[str]
    status: str
    created_by: Optional[int]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    agent_ids: list[int]

    class Config:
        from_attributes = True


class ProjectDetailResponse(ProjectResponse):
    next_step: str
    task_summary: dict



def _project_agent_ids(project: Project) -> list[int]:
    if not project.agent_ids_json:
        return []
    try:
        return json.loads(project.agent_ids_json)
    except json.JSONDecodeError:
        return []



def _build_project_response(project: Project, next_step: Optional[str] = None, task_summary: Optional[dict] = None) -> ProjectResponse | ProjectDetailResponse:
    payload = {
        'id': project.id,
        'name': project.name,
        'goal': project.goal,
        'git_repo_url': project.git_repo_url,
        'collaboration_dir': project.collaboration_dir,
        'status': project.status,
        'created_by': project.created_by,
        'created_at': project.created_at,
        'updated_at': project.updated_at,
        'agent_ids': _project_agent_ids(project),
    }
    if next_step is not None and task_summary is not None:
        return ProjectDetailResponse(next_step=next_step, task_summary=task_summary, **payload)
    return ProjectResponse(**payload)



def _validate_agent_ids(db: Session, agent_ids: list[int]) -> list[int]:
    if not agent_ids:
        raise HTTPException(status_code=400, detail='At least one agent must be selected')
    agents = db.query(Agent).filter(Agent.id.in_(agent_ids)).all()
    if len(agents) != len(agent_ids):
        raise HTTPException(status_code=400, detail='Some agent_ids are invalid')
    return agent_ids



def compute_next_step(db: Session, project: Project) -> tuple[str, dict]:
    tasks = db.query(Task).filter(Task.project_id == project.id).all()
    plans = db.query(ProjectPlan).filter(ProjectPlan.project_id == project.id).all()
    summary = {
        'total': len(tasks),
        'pending': sum(1 for t in tasks if t.status == 'pending'),
        'running': sum(1 for t in tasks if t.status == 'running'),
        'completed': sum(1 for t in tasks if t.status == 'completed'),
        'needs_attention': sum(1 for t in tasks if t.status == 'needs_attention'),
        'abandoned': sum(1 for t in tasks if t.status == 'abandoned'),
    }

    if project.status == 'draft':
        return 'Create project plan', summary

    if project.status == 'planning':
        running_plans = sum(1 for plan in plans if plan.status == 'running')
        completed_plans = sum(1 for plan in plans if plan.status in ('completed', 'final') and plan.plan_json)
        if running_plans > 0:
            return 'Waiting for plan generation', summary
        if completed_plans > 0:
            return 'Review and finalize plan', summary
        return 'Create project plan', summary

    if project.status == 'executing':
        if tasks and all(t.status in ('completed', 'abandoned') for t in tasks):
            return 'View execution summary', summary

        completed_codes = {t.task_code for t in tasks if t.status in ('completed', 'abandoned')}
        for t in tasks:
            if t.status == 'pending':
                deps = json.loads(t.depends_on_json) if t.depends_on_json else []
                if all(d in completed_codes for d in deps):
                    return f'Dispatch task: {t.task_code} - {t.task_name}', summary

        if any(t.status == 'running' for t in tasks):
            return 'Waiting for running tasks to complete', summary
        if any(t.status == 'needs_attention' for t in tasks):
            return 'Handle tasks that need attention', summary
        return 'View execution summary', summary

    if project.status == 'completed':
        return 'View execution summary', summary

    return 'No action available', summary


@router.get('', response_model=list[ProjectResponse])
def list_projects(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return [_build_project_response(project) for project in db.query(Project).all()]


@router.post('', response_model=ProjectResponse, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent_ids = _validate_agent_ids(db, body.agent_ids)
    project = Project(
        name=body.name,
        goal=body.goal,
        git_repo_url=body.git_repo_url,
        collaboration_dir=body.collaboration_dir,
        created_by=user.id,
        agent_ids_json=json.dumps(agent_ids),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _build_project_response(project)


@router.get('/{project_id}', response_model=ProjectDetailResponse)
def get_project(project_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail='Project not found')
    next_step, task_summary = compute_next_step(db, project)
    return _build_project_response(project, next_step=next_step, task_summary=task_summary)


@router.put('/{project_id}', response_model=ProjectResponse)
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail='Project not found')
    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    if 'agent_ids' in update_data:
        update_data['agent_ids_json'] = json.dumps(_validate_agent_ids(db, update_data.pop('agent_ids')))
    for key, value in update_data.items():
        setattr(project, key, value)
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    return _build_project_response(project)


@router.delete('/{project_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail='Project not found')

    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    task_ids = [task.id for task in tasks]
    if task_ids:
        db.query(TaskEvent).filter(TaskEvent.task_id.in_(task_ids)).delete(synchronize_session=False)
    db.query(Task).filter(Task.project_id == project_id).delete(synchronize_session=False)
    db.query(ProjectPlan).filter(ProjectPlan.project_id == project_id).delete(synchronize_session=False)
    db.delete(project)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
