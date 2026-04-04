from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, Text, Boolean, DateTime, ForeignKey,
)
from database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(Text, unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False)
    slug = Column(Text, unique=True, nullable=False)
    agent_type = Column(Text, nullable=False)
    model_name = Column(Text)
    capability = Column(Text)
    machine_label = Column(Text)
    is_active = Column(Boolean, default=True)
    availability_status = Column(Text, default="unknown")  # online/quota_exhausted/expired/unknown
    subscription_expires_at = Column(DateTime, nullable=True)
    short_term_reset_at = Column(DateTime, nullable=True)
    short_term_reset_interval_hours = Column(Integer, nullable=True)
    long_term_reset_at = Column(DateTime, nullable=True)
    long_term_reset_interval_days = Column(Integer, nullable=True)
    last_usage_update_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False)
    goal = Column(Text)
    git_repo_url = Column(Text)
    collaboration_dir = Column(Text)
    status = Column(Text, default="draft")  # draft/planning/executing/completed/abandoned
    agent_ids_json = Column(Text, default="[]")  # JSON array of agent IDs participating in project
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ProjectPlan(Base):
    __tablename__ = "project_plans"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    source_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    plan_type = Column(Text, default="candidate")  # candidate/final
    plan_json = Column(Text)
    prompt_text = Column(Text)
    status = Column(Text, default="completed")  # pending/running/completed/needs_attention/final
    source_path = Column(Text)
    include_usage = Column(Boolean, default=False)
    selected_agent_ids_json = Column(Text, default="[]")
    dispatched_at = Column(DateTime, nullable=True)
    detected_at = Column(DateTime, nullable=True)
    last_error = Column(Text)
    is_selected = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("project_plans.id"), nullable=False)
    task_code = Column(Text, unique=True, nullable=False)
    task_name = Column(Text, nullable=False)
    description = Column(Text)
    assignee_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    status = Column(Text, default="pending")  # pending/running/completed/needs_attention/abandoned
    depends_on_json = Column(Text, default="[]")
    expected_output_path = Column(Text)
    result_file_path = Column(Text)
    usage_file_path = Column(Text)
    last_error = Column(Text)
    timeout_minutes = Column(Integer, default=10)
    dispatched_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class TaskEvent(Base):
    __tablename__ = "task_events"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    event_type = Column(Text, nullable=False)  # dispatched/completed/timeout/manual_complete/abandoned/redispatched/error
    detail = Column(Text)
    created_at = Column(DateTime, default=utcnow)
