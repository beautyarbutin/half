from datetime import datetime, timedelta, timezone
from typing import Literal

from models import Agent

BEIJING_TZ = timezone(timedelta(hours=8))
DerivedAgentStatus = Literal["available", "unavailable", "short_reset_pending", "long_reset_pending"]


def now_beijing_naive() -> datetime:
    return datetime.now(BEIJING_TZ).replace(tzinfo=None, second=0, microsecond=0)


def derive_agent_status(agent: Agent, now: datetime | None = None) -> DerivedAgentStatus:
    current = now or now_beijing_naive()

    if agent.subscription_expires_at and agent.subscription_expires_at <= current:
        return "unavailable"

    if agent.availability_status == "short_reset_pending":
        if agent.short_term_reset_at and agent.short_term_reset_at > current:
            return "short_reset_pending"
        return "available"

    if agent.availability_status == "long_reset_pending":
        if agent.long_term_reset_at and agent.long_term_reset_at > current:
            return "long_reset_pending"
        return "available"

    return "available"
