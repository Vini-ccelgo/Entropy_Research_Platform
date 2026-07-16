PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS hypotheses (
    id TEXT NOT NULL, revision INTEGER NOT NULL, content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL, PRIMARY KEY (id, revision)
);
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY, trial_id TEXT NOT NULL, observer_id TEXT NOT NULL,
    payload_json TEXT NOT NULL, recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_observations_trial ON observations(trial_id);

CREATE TABLE IF NOT EXISTS research_questions (
    id TEXT NOT NULL, revision INTEGER NOT NULL, content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL, PRIMARY KEY (id, revision)
);
CREATE TABLE IF NOT EXISTS journal_entries (
    id TEXT NOT NULL, revision INTEGER NOT NULL, content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL, PRIMARY KEY (id, revision)
);
CREATE TABLE IF NOT EXISTS claims (
    id TEXT NOT NULL, revision INTEGER NOT NULL, content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL, PRIMARY KEY (id, revision)
);
CREATE TABLE IF NOT EXISTS external_references (
    id TEXT NOT NULL, revision INTEGER NOT NULL, content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL, PRIMARY KEY (id, revision)
);
CREATE TABLE IF NOT EXISTS scientific_relations (
    id TEXT PRIMARY KEY, source_type TEXT NOT NULL, source_id TEXT NOT NULL,
    source_revision INTEGER NOT NULL, relation_type TEXT NOT NULL,
    target_type TEXT NOT NULL, target_id TEXT NOT NULL, target_revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS belief_assessments (
    id TEXT PRIMARY KEY, hypothesis_id TEXT NOT NULL, hypothesis_revision INTEGER NOT NULL,
    observer_id TEXT NOT NULL, assessed_at TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY, action TEXT NOT NULL, subject_type TEXT, subject_id TEXT,
    subject_revision INTEGER, actor_id TEXT NOT NULL, occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_relations_source ON scientific_relations(source_type, source_id, source_revision);
CREATE INDEX IF NOT EXISTS idx_relations_target ON scientific_relations(target_type, target_id, target_revision);
CREATE INDEX IF NOT EXISTS idx_audit_subject ON audit_events(subject_type, subject_id, subject_revision);

CREATE TABLE IF NOT EXISTS experiment_revisions (
    id TEXT NOT NULL, revision INTEGER NOT NULL, content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL, PRIMARY KEY (id, revision)
);
CREATE TABLE IF NOT EXISTS trial_executions (
    id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL, experiment_revision INTEGER NOT NULL,
    trial_spec_id TEXT NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL,
    started_at TEXT NOT NULL, finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_trial_executions_experiment
    ON trial_executions(experiment_id, experiment_revision);
CREATE TABLE IF NOT EXISTS experiment_runs (id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL, state TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trial_attempts (id TEXT PRIMARY KEY, experiment_run_id TEXT NOT NULL, trial_spec_id TEXT NOT NULL, idempotency_key TEXT UNIQUE NOT NULL, state TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS control_events (id TEXT PRIMARY KEY, experiment_run_id TEXT NOT NULL, trial_attempt_id TEXT, event_type TEXT NOT NULL, payload_json TEXT NOT NULL, occurred_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_attempts_run ON trial_attempts(experiment_run_id);
CREATE TABLE IF NOT EXISTS entropy_policy_specifications (id TEXT NOT NULL, revision INTEGER NOT NULL, content_hash TEXT NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY(id,revision));
CREATE TABLE IF NOT EXISTS analysis_specifications (id TEXT NOT NULL, revision INTEGER NOT NULL, content_hash TEXT NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY(id,revision));
CREATE TABLE IF NOT EXISTS analysis_runs (id TEXT PRIMARY KEY, status TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS analysis_results (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL);
