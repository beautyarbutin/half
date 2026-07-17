from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user
from models import User
from services.secure_handoff_experiment import (
    add_intervention,
    evaluate_run,
    exclude_run_from_analysis,
    get_run_prompt,
    list_experiments,
    load_run,
    prepare_run,
    secure_arm_options,
    submit_manual_attempt,
    summarize_experiment,
    update_run_usage,
)


router = APIRouter(prefix="/api/handoff-experiments", tags=["handoff-experiments"])


class PrepareRunRequest(BaseModel):
    arm_id: str
    model: str = "gpt-5.5"
    max_attempts: int | None = Field(default=None, ge=1, le=10)


class AttemptUsage(BaseModel):
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class SubmitAttemptRequest(BaseModel):
    conversation_id: str | None = None
    usage: AttemptUsage = Field(default_factory=AttemptUsage)
    notes: str = ""
    agent_output: str = ""
    trace_jsonl: str = ""
    trace_complete: bool = False


class InterventionRequest(BaseModel):
    kind: str
    detail: str
    minutes: float = Field(default=0, ge=0)


class ExcludeRunRequest(BaseModel):
    reason: str = Field(min_length=1)


@router.get("")
def experiments(user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    _ = user
    return list_experiments()


@router.get("/arms")
def experiment_arms(user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    _ = user
    return secure_arm_options()


@router.post("/{experiment_id}/runs")
def create_experiment_run(
    experiment_id: str,
    body: PrepareRunRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _ = user
    try:
        run = prepare_run(
            experiment_id,
            body.arm_id,
            model=body.model,
            max_attempts=body.max_attempts,
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return run


@router.get("/runs/{run_id}")
def get_experiment_run(run_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    _ = user
    try:
        return load_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/prompt")
def experiment_run_prompt(run_id: str, user: User = Depends(get_current_user)) -> dict[str, str]:
    _ = user
    try:
        return get_run_prompt(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/attempts")
def submit_experiment_attempt(
    run_id: str,
    body: SubmitAttemptRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _ = user
    try:
        return submit_manual_attempt(
            run_id,
            conversation_id=body.conversation_id,
            usage=body.usage.model_dump(),
            notes=body.notes,
            agent_output=body.agent_output,
            trace_jsonl=body.trace_jsonl,
            trace_complete=body.trace_complete,
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{run_id}/evaluate")
def evaluate_experiment_run(run_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    _ = user
    try:
        return evaluate_run(run_id)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/runs/{run_id}/usage")
def update_experiment_run_usage(
    run_id: str,
    body: AttemptUsage,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _ = user
    try:
        return update_run_usage(run_id, body.model_dump())
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{run_id}/exclude")
def exclude_experiment_run(
    run_id: str,
    body: ExcludeRunRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _ = user
    try:
        return exclude_run_from_analysis(run_id, body.reason)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{run_id}/interventions")
def record_intervention(
    run_id: str,
    body: InterventionRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _ = user
    try:
        return add_intervention(
            run_id,
            kind=body.kind,
            detail=body.detail,
            minutes=body.minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{experiment_id}/summary")
def experiment_summary(experiment_id: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    _ = user
    return summarize_experiment(experiment_id)
