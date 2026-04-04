import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Agent, Project, Task, User
from auth import get_current_user

router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str
    agent_type: str
    model_name: Optional[str] = None
    capability: Optional[str] = None
    machine_label: Optional[str] = None
    is_active: bool = True
    availability_status: str = "unknown"
    subscription_expires_at: Optional[datetime] = None
    short_term_reset_at: Optional[datetime] = None
    short_term_reset_interval_hours: Optional[int] = None
    long_term_reset_at: Optional[datetime] = None
    long_term_reset_interval_days: Optional[int] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    agent_type: Optional[str] = None
    model_name: Optional[str] = None
    capability: Optional[str] = None
    machine_label: Optional[str] = None
    is_active: Optional[bool] = None
    availability_status: Optional[str] = None
    subscription_expires_at: Optional[datetime] = None
    short_term_reset_at: Optional[datetime] = None
    short_term_reset_interval_hours: Optional[int] = None
    long_term_reset_at: Optional[datetime] = None
    long_term_reset_interval_days: Optional[int] = None


class AgentResponse(BaseModel):
    id: int
    name: str
    slug: str
    agent_type: str
    model_name: Optional[str]
    capability: Optional[str]
    machine_label: Optional[str]
    is_active: bool
    availability_status: str
    subscription_expires_at: Optional[datetime]
    short_term_reset_at: Optional[datetime]
    short_term_reset_interval_hours: Optional[int]
    long_term_reset_at: Optional[datetime]
    long_term_reset_interval_days: Optional[int]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


def _slugify(name: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized or "agent"



def _generate_unique_slug(db: Session, name: str) -> str:
    base = _slugify(name)
    candidate = base
    index = 2
    while db.query(Agent).filter(Agent.slug == candidate).first():
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _advance_reset_time(current: Optional[datetime], interval: Optional[int], *, hours: bool) -> Optional[datetime]:
    if not current or not interval or interval <= 0:
        return current
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    step = timedelta(hours=interval) if hours else timedelta(days=interval)
    while current <= now:
        current = current + step
    return current


def _normalize_agent_reset_times(agent: Agent) -> bool:
    next_short = _advance_reset_time(agent.short_term_reset_at, agent.short_term_reset_interval_hours, hours=True)
    next_long = _advance_reset_time(agent.long_term_reset_at, agent.long_term_reset_interval_days, hours=False)
    changed = next_short != agent.short_term_reset_at or next_long != agent.long_term_reset_at
    if changed:
        agent.short_term_reset_at = next_short
        agent.long_term_reset_at = next_long
        agent.updated_at = datetime.now(timezone.utc)
    return changed



@router.get("", response_model=list[AgentResponse])
def list_agents(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    agents = db.query(Agent).all()
    changed = False
    for agent in agents:
        changed = _normalize_agent_reset_times(agent) or changed
    if changed:
        db.commit()
        for agent in agents:
            db.refresh(agent)
    return agents


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
def create_agent(body: AgentCreate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    payload = body.model_dump()
    payload["slug"] = _generate_unique_slug(db, body.name)
    agent = Agent(**payload)
    _normalize_agent_reset_times(agent)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.put("/{agent_id}", response_model=AgentResponse)
def update_agent(agent_id: int, body: AgentUpdate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(agent, key, value)
    _normalize_agent_reset_times(agent)
    agent.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    task_ref = db.query(Task).filter(Task.assignee_agent_id == agent_id).first()
    if task_ref:
        raise HTTPException(status_code=400, detail="Agent 已关联任务，无法删除")

    for project in db.query(Project).all():
        agent_ids = json.loads(project.agent_ids_json or "[]")
        if agent_id in agent_ids:
            raise HTTPException(status_code=400, detail="Agent 已关联项目，无法删除")

    db.delete(agent)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
