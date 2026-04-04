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
BEIJING_TZ = timezone(timedelta(hours=8))


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
    short_term_reset_needs_confirmation: bool
    long_term_reset_at: Optional[datetime]
    long_term_reset_interval_days: Optional[int]
    long_term_reset_needs_confirmation: bool
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


def _normalize_beijing_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(second=0, microsecond=0)
    return value.astimezone(BEIJING_TZ).replace(tzinfo=None, second=0, microsecond=0)


def _normalize_agent_input(payload: dict) -> dict:
    for field in ("short_term_reset_at", "long_term_reset_at"):
        if field in payload:
            payload[field] = _normalize_beijing_datetime(payload[field])
    return payload


def _now_beijing_naive() -> datetime:
    return datetime.now(BEIJING_TZ).replace(tzinfo=None, second=0, microsecond=0)


def _advance_reset_time(current: Optional[datetime], interval: Optional[int], *, hours: bool) -> Optional[datetime]:
    if not current or not interval or interval <= 0:
        return current
    if current.tzinfo is None:
        current = current.replace(tzinfo=BEIJING_TZ)
    else:
        current = current.astimezone(BEIJING_TZ)
    now = datetime.now(BEIJING_TZ)
    step = timedelta(hours=interval) if hours else timedelta(days=interval)
    while current <= now:
        current = current + step
    return current.replace(tzinfo=None)


def _normalize_agent_reset_times(agent: Agent, *, mark_confirmation: bool) -> bool:
    next_short = _advance_reset_time(agent.short_term_reset_at, agent.short_term_reset_interval_hours, hours=True)
    next_long = _advance_reset_time(agent.long_term_reset_at, agent.long_term_reset_interval_days, hours=False)
    changed = next_short != agent.short_term_reset_at or next_long != agent.long_term_reset_at
    if changed:
        if mark_confirmation and next_short != agent.short_term_reset_at:
            agent.short_term_reset_needs_confirmation = True
        if mark_confirmation and next_long != agent.long_term_reset_at:
            agent.long_term_reset_needs_confirmation = True
        agent.short_term_reset_at = next_short
        agent.long_term_reset_at = next_long
        agent.updated_at = datetime.now(timezone.utc)
    return changed


def _clear_confirmation_flags_on_manual_update(agent: Agent, update_data: dict):
    if "short_term_reset_at" in update_data or "short_term_reset_interval_hours" in update_data:
        agent.short_term_reset_needs_confirmation = False
    if "long_term_reset_at" in update_data or "long_term_reset_interval_days" in update_data:
        agent.long_term_reset_needs_confirmation = False


def _get_agent_or_404(db: Session, agent_id: int) -> Agent:
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent



@router.get("", response_model=list[AgentResponse])
def list_agents(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    agents = db.query(Agent).all()
    changed = False
    for agent in agents:
        changed = _normalize_agent_reset_times(agent, mark_confirmation=True) or changed
    if changed:
        db.commit()
        for agent in agents:
            db.refresh(agent)
    return agents


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
def create_agent(body: AgentCreate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    payload = _normalize_agent_input(body.model_dump())
    payload["slug"] = _generate_unique_slug(db, body.name)
    agent = Agent(**payload)
    _normalize_agent_reset_times(agent, mark_confirmation=False)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.put("/{agent_id}", response_model=AgentResponse)
def update_agent(agent_id: int, body: AgentUpdate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    agent = _get_agent_or_404(db, agent_id)
    update_data = _normalize_agent_input(body.model_dump(exclude_unset=True))
    for key, value in update_data.items():
        setattr(agent, key, value)
    _clear_confirmation_flags_on_manual_update(agent, update_data)
    _normalize_agent_reset_times(agent, mark_confirmation=False)
    agent.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(agent)
    return agent


@router.post("/{agent_id}/short-term-reset/reset", response_model=AgentResponse)
def reset_short_term(agent_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    agent = _get_agent_or_404(db, agent_id)
    if not agent.short_term_reset_at or not agent.short_term_reset_interval_hours:
        raise HTTPException(status_code=400, detail="短期重置时间或间隔未设置")
    agent.short_term_reset_at = _now_beijing_naive() + timedelta(hours=agent.short_term_reset_interval_hours)
    agent.short_term_reset_needs_confirmation = False
    agent.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(agent)
    return agent


@router.post("/{agent_id}/short-term-reset/confirm", response_model=AgentResponse)
def confirm_short_term(agent_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    agent = _get_agent_or_404(db, agent_id)
    agent.short_term_reset_needs_confirmation = False
    agent.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(agent)
    return agent


@router.post("/{agent_id}/long-term-reset/reset", response_model=AgentResponse)
def reset_long_term(agent_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    agent = _get_agent_or_404(db, agent_id)
    if not agent.long_term_reset_at or not agent.long_term_reset_interval_days:
        raise HTTPException(status_code=400, detail="长期重置时间或间隔未设置")
    agent.long_term_reset_at = _now_beijing_naive() + timedelta(days=agent.long_term_reset_interval_days)
    agent.long_term_reset_needs_confirmation = False
    agent.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(agent)
    return agent


@router.post("/{agent_id}/long-term-reset/confirm", response_model=AgentResponse)
def confirm_long_term(agent_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    agent = _get_agent_or_404(db, agent_id)
    agent.long_term_reset_needs_confirmation = False
    agent.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    agent = _get_agent_or_404(db, agent_id)

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
