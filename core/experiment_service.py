"""Control-plane service for validated, idempotent experiment execution."""
from __future__ import annotations

from time import sleep
from uuid import UUID

from core.control import (
    ControlEvent, ControlEventType, ErrorCategory, ExperimentRun, ExperimentRunState,
    RetryPolicy, TrialAttempt, TrialAttemptState,
)
from core.interfaces import ControlRepositoryPort, ScientificRecordRepositoryPort
from core.provenance import canonical_hash
from core.science import ExperimentRevision
from runner.scheduler import Scheduler


class ExperimentService:
    def __init__(self, records: ScientificRecordRepositoryPort, control: ControlRepositoryPort,
                 scheduler: Scheduler, orchestrator, actor_id: UUID) -> None:
        self._records, self._control = records, control
        self._scheduler, self._orchestrator, self._actor_id = scheduler, orchestrator, actor_id

    def register(self, experiment: ExperimentRevision):
        return self._records.register_experiment_revision(experiment)

    def start(self, experiment: ExperimentRevision, idempotency_key: str,
              retry_policy: RetryPolicy | None = None) -> ExperimentRun:
        self._records.resolve_scientific_record(experiment.reference())
        policy = retry_policy or RetryPolicy()
        command_hash = canonical_hash({"experiment": experiment.reference().model_dump(mode="json"), "policy": policy.model_dump(mode="json"), "scheduler": self._scheduler.name})
        existing = self._control.find_run_by_key(idempotency_key)
        if existing:
            if existing.command_hash != command_hash:
                raise ValueError("idempotency key is already bound to a different start command")
            return existing
        run = ExperimentRun(experiment_revision=experiment.reference(), idempotency_key=idempotency_key,
                            command_hash=command_hash, retry_policy=policy,
                            scheduler_name=self._scheduler.name, created_by=self._actor_id)
        run = self._control.create_run(run, self._event(ControlEventType.RUN_CREATED, run.id, to_state=run.state))
        self._scheduler.submit(lambda: self._run(experiment, run))
        return self._control.get_run(run.id)

    def cancel(self, run_id: UUID) -> ExperimentRun:
        run = self._control.get_run(run_id)
        return self._control.transition_run(run_id, ExperimentRunState.CANCELLED,
                                            self._event(ControlEventType.CANCELLATION_REQUESTED, run_id,
                                                        from_state=run.state, to_state=ExperimentRunState.CANCELLED))

    def _run(self, experiment: ExperimentRevision, initial: ExperimentRun) -> None:
        run = self._control.get_run(initial.id)
        if run.state is ExperimentRunState.CANCELLED:
            return
        run = self._control.transition_run(run.id, ExperimentRunState.RUNNING,
                                           self._event(ControlEventType.STATE_CHANGED, run.id,
                                                       from_state=run.state, to_state=ExperimentRunState.RUNNING))
        failed = False
        for trial in experiment.plan.trials:
            if self._control.get_run(run.id).state is ExperimentRunState.CANCELLED:
                return
            if not self._execute_with_retries(experiment, run, trial):
                failed = True
        run = self._control.get_run(run.id)
        if run.state is ExperimentRunState.RUNNING:
            target = ExperimentRunState.FAILED if failed else ExperimentRunState.COMPLETED
            self._control.transition_run(run.id, target,
                                         self._event(ControlEventType.STATE_CHANGED, run.id,
                                                     from_state=run.state, to_state=target))

    def _execute_with_retries(self, experiment: ExperimentRevision, run: ExperimentRun, trial) -> bool:
        predecessor = None
        for number in range(1, run.retry_policy.max_attempts + 1):
            attempt = TrialAttempt(experiment_run_id=run.id, trial_spec_id=trial.id, attempt_number=number,
                                   idempotency_key=f"{run.id}:{trial.id}:{number}", predecessor_attempt_id=predecessor)
            attempt = self._control.create_attempt(attempt, self._event(ControlEventType.ATTEMPT_CREATED, run.id, attempt.id, to_state=attempt.state))
            attempt = self._control.transition_attempt(attempt.id, TrialAttemptState.SCHEDULED,
                self._event(ControlEventType.STATE_CHANGED, run.id, attempt.id, attempt.state, TrialAttemptState.SCHEDULED))
            attempt = self._control.transition_attempt(attempt.id, TrialAttemptState.RUNNING,
                self._event(ControlEventType.STATE_CHANGED, run.id, attempt.id, attempt.state, TrialAttemptState.RUNNING))
            execution = self._orchestrator.execute(experiment, trial, run.id, attempt.id, number, attempt.idempotency_key)
            if execution.status.value == "completed":
                self._control.finalize_attempt(execution, TrialAttemptState.SUCCEEDED,
                    self._event(ControlEventType.STATE_CHANGED, run.id, attempt.id, TrialAttemptState.RUNNING, TrialAttemptState.SUCCEEDED))
                return True
            category = ErrorCategory(execution.failure_category or ErrorCategory.UNKNOWN.value)
            self._control.finalize_attempt(execution, TrialAttemptState.FAILED,
                self._event(ControlEventType.FAILURE_RECORDED, run.id, attempt.id, TrialAttemptState.RUNNING, TrialAttemptState.FAILED), category, execution.error)
            predecessor = attempt.id
            if category not in run.retry_policy.retryable or number == run.retry_policy.max_attempts:
                return False
            self._control.append_control_event(self._event(ControlEventType.RETRY_SCHEDULED, run.id, attempt.id,
                TrialAttemptState.FAILED, TrialAttemptState.SCHEDULED, {"next_attempt": str(number + 1), "backoff_seconds": str(run.retry_policy.backoff_seconds), "category": category.value}))
            sleep(run.retry_policy.backoff_seconds)
        return False

    def _event(self, event_type, run_id, attempt_id=None, from_state=None, to_state=None, details=None) -> ControlEvent:
        return ControlEvent(event_type=event_type, actor_id=self._actor_id, experiment_run_id=run_id,
                            trial_attempt_id=attempt_id, from_state=from_state, to_state=to_state,
                            details=details or {})
