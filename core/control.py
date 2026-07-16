"""Explicit operational state; separate from immutable scientific evidence."""
from __future__ import annotations
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4
from typing import TypeAlias
from pydantic import Field
from core.provenance import canonical_hash
from core.science import ScientificRecordReference
from core.types import FrozenModel, utc_now

class ExperimentRunState(StrEnum):
    SCHEDULED="scheduled"; RUNNING="running"; PAUSED="paused"; COMPLETED="completed"; FAILED="failed"; CANCELLED="cancelled"; ARCHIVED="archived"
class TrialAttemptState(StrEnum):
    PLANNED="planned"; SCHEDULED="scheduled"; RUNNING="running"; SUCCEEDED="succeeded"; FAILED="failed"; CANCELLED="cancelled"; ARCHIVED="archived"
class ControlEventType(StrEnum):
    RUN_CREATED="run_created"; ATTEMPT_CREATED="attempt_created"; STATE_CHANGED="state_changed"; RETRY_SCHEDULED="retry_scheduled"; CANCELLATION_REQUESTED="cancellation_requested"; FAILURE_RECORDED="failure_recorded"
class ErrorCategory(StrEnum):
    VALIDATION="validation"; TRANSIENT="transient"; PROVIDER="provider"; INTERRUPTED="interrupted"; CONFIGURATION="configuration"; UNKNOWN="unknown"
ControlState: TypeAlias = ExperimentRunState | TrialAttemptState

class RetryPolicy(FrozenModel):
    max_attempts: int = Field(default=1, ge=1, le=100)
    retryable: tuple[ErrorCategory,...] = (ErrorCategory.TRANSIENT, ErrorCategory.PROVIDER)
    backoff_seconds: float = Field(default=0, ge=0)
    def content_hash(self)->str: return canonical_hash(self.model_dump(mode="json"))

class ExperimentRun(FrozenModel):
    id: UUID=Field(default_factory=uuid4); experiment_revision: ScientificRecordReference
    idempotency_key: str=Field(min_length=1,max_length=200); command_hash: str=Field(min_length=64,max_length=64); retry_policy: RetryPolicy
    scheduler_name: str; created_by: UUID; state: ExperimentRunState=ExperimentRunState.SCHEDULED
    created_at: datetime=Field(default_factory=utc_now); updated_at: datetime=Field(default_factory=utc_now)

class TrialAttempt(FrozenModel):
    id: UUID=Field(default_factory=uuid4); experiment_run_id: UUID; trial_spec_id: UUID
    attempt_number: int=Field(ge=1); idempotency_key: str=Field(min_length=1,max_length=240)
    predecessor_attempt_id: UUID|None=None; state: TrialAttemptState=TrialAttemptState.PLANNED
    created_at: datetime=Field(default_factory=utc_now); updated_at: datetime=Field(default_factory=utc_now)
    error_category: ErrorCategory|None=None; error_message: str|None=None

class ControlEvent(FrozenModel):
    id: UUID=Field(default_factory=uuid4); event_type: ControlEventType; actor_id: UUID
    experiment_run_id: UUID; trial_attempt_id: UUID|None=None
    from_state: ControlState|None=None; to_state: ControlState|None=None; details: dict[str,str]=Field(default_factory=dict)
    occurred_at: datetime=Field(default_factory=utc_now)

RUN_TRANSITIONS={
 ExperimentRunState.SCHEDULED:{ExperimentRunState.RUNNING,ExperimentRunState.CANCELLED},
 ExperimentRunState.RUNNING:{ExperimentRunState.PAUSED,ExperimentRunState.COMPLETED,ExperimentRunState.FAILED,ExperimentRunState.CANCELLED},
 ExperimentRunState.PAUSED:{ExperimentRunState.RUNNING,ExperimentRunState.CANCELLED},
 ExperimentRunState.COMPLETED:{ExperimentRunState.ARCHIVED}, ExperimentRunState.FAILED:{ExperimentRunState.ARCHIVED}, ExperimentRunState.CANCELLED:{ExperimentRunState.ARCHIVED}, ExperimentRunState.ARCHIVED:set()}
ATTEMPT_TRANSITIONS={
 TrialAttemptState.PLANNED:{TrialAttemptState.SCHEDULED,TrialAttemptState.CANCELLED}, TrialAttemptState.SCHEDULED:{TrialAttemptState.RUNNING,TrialAttemptState.CANCELLED},
 TrialAttemptState.RUNNING:{TrialAttemptState.SUCCEEDED,TrialAttemptState.FAILED,TrialAttemptState.CANCELLED}, TrialAttemptState.SUCCEEDED:{TrialAttemptState.ARCHIVED},TrialAttemptState.FAILED:{TrialAttemptState.ARCHIVED},TrialAttemptState.CANCELLED:{TrialAttemptState.ARCHIVED},TrialAttemptState.ARCHIVED:set()}

def require_transition(current, target, table)->None:
    if target not in table[current]: raise ValueError(f"invalid state transition: {current} -> {target}")
