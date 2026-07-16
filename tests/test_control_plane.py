from pathlib import Path
from uuid import uuid4
from core.control import *
from core.science import ScientificRecordReference, ScientificRecordType
from database.sqlite_repository import SqliteRepository

def test_control_state_and_idempotency_are_auditable(tmp_path:Path)->None:
    require_transition(ExperimentRunState.SCHEDULED, ExperimentRunState.RUNNING, RUN_TRANSITIONS)
    require_transition(TrialAttemptState.RUNNING, TrialAttemptState.SUCCEEDED, ATTEMPT_TRANSITIONS)
    try:
        require_transition(ExperimentRunState.COMPLETED, ExperimentRunState.RUNNING, RUN_TRANSITIONS)
    except ValueError:
        return
    raise AssertionError("terminal runs must not restart")
