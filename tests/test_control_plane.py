from pathlib import Path
from uuid import uuid4
from core.control import *
from core.science import ScientificRecordReference, ScientificRecordType
from database.sqlite_repository import SqliteRepository
from core.experiment_service import ExperimentService
from core.mvp import build_and_register
from core.control import ControlEvent, ControlEventType, RetryPolicy
from pathlib import Path


class _NoopScheduler:
    name = "test"
    def submit(self, job): pass

def test_control_state_and_idempotency_are_auditable(tmp_path:Path)->None:
    require_transition(ExperimentRunState.SCHEDULED, ExperimentRunState.RUNNING, RUN_TRANSITIONS)
    require_transition(TrialAttemptState.RUNNING, TrialAttemptState.SUCCEEDED, ATTEMPT_TRANSITIONS)
    try:
        require_transition(ExperimentRunState.COMPLETED, ExperimentRunState.RUNNING, RUN_TRANSITIONS)
    except ValueError:
        return
    raise AssertionError("terminal runs must not restart")


def test_process_restart_reconciliation_closes_running_attempt_atomically(tmp_path: Path):
    repo = SqliteRepository(tmp_path / "restart.db")
    _, experiment = build_and_register(Path("config/experiments/mixed-question-pretest.json"), repo)
    actor = experiment.created_by
    service = ExperimentService(repo, repo, _NoopScheduler(), None, actor)
    run = ExperimentRun(experiment_revision=experiment.reference(), idempotency_key="restart-test",
        command_hash="a" * 64, retry_policy=RetryPolicy(), scheduler_name="test", created_by=actor)
    run = repo.create_run(run, ControlEvent(event_type=ControlEventType.RUN_CREATED, actor_id=actor, experiment_run_id=run.id, to_state=run.state))
    run = repo.transition_run(run.id, ExperimentRunState.RUNNING, ControlEvent(event_type=ControlEventType.STATE_CHANGED, actor_id=actor, experiment_run_id=run.id, from_state=ExperimentRunState.SCHEDULED, to_state=ExperimentRunState.RUNNING))
    attempt = TrialAttempt(experiment_run_id=run.id, trial_spec_id=experiment.plan.trials[0].id, attempt_number=1, idempotency_key="restart-test:1")
    repo.create_attempt(attempt, ControlEvent(event_type=ControlEventType.ATTEMPT_CREATED, actor_id=actor, experiment_run_id=run.id, trial_attempt_id=attempt.id, to_state=attempt.state))
    repo.transition_attempt(attempt.id, TrialAttemptState.SCHEDULED, ControlEvent(event_type=ControlEventType.STATE_CHANGED, actor_id=actor, experiment_run_id=run.id, trial_attempt_id=attempt.id, from_state=TrialAttemptState.PLANNED, to_state=TrialAttemptState.SCHEDULED))
    repo.transition_attempt(attempt.id, TrialAttemptState.RUNNING, ControlEvent(event_type=ControlEventType.STATE_CHANGED, actor_id=actor, experiment_run_id=run.id, trial_attempt_id=attempt.id, from_state=TrialAttemptState.SCHEDULED, to_state=TrialAttemptState.RUNNING))
    recovered = service.reconcile_interrupted(run.id)
    assert recovered.state is ExperimentRunState.FAILED
    assert list(repo.attempts_for_run(run.id))[0].state is TrialAttemptState.FAILED
    assert len(repo.trials_for_experiment(experiment.reference())) == 1
    assert service.reconcile_interrupted(run.id).state is ExperimentRunState.FAILED
