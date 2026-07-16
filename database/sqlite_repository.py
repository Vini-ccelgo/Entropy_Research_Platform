"""SQLite persistence adapter for plans, trial results, and observations."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID, uuid4

from core.interfaces import ControlRepositoryPort, ExperimentRepositoryPort, HypothesisRegistryPort, ScientificRecordRepositoryPort
from core.control import ControlEvent, ExperimentRun, ExperimentRunState, TrialAttempt, TrialAttemptState, require_transition, RUN_TRANSITIONS, ATTEMPT_TRANSITIONS
from core.science import (
    AuditAction, AuditEvent, BeliefAssessment, Claim, ExperimentRevision, ExternalReference, JournalEntry,
    ResearchQuestion, ScientificRecordReference, ScientificRecordType, ScientificRelation,
)
from core.provenance import TrialExecution
from entropy.policy import EntropyPolicySpecification, EntropyPolicyReference
from analysis.domain import AnalysisSpecification, AnalysisRun, AnalysisResult, CohortSnapshot
from core.types import Hypothesis, HypothesisReference, Observation


class SqliteRepository(ExperimentRepositoryPort, HypothesisRegistryPort, ScientificRecordRepositoryPort, ControlRepositoryPort):
    """Transactional local adapter; PostgreSQL can replace it without domain changes."""
    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._connection.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))

    def close(self) -> None:
        self._connection.close()

    def register(self, hypothesis: Hypothesis) -> HypothesisReference:
        reference = self.register_hypothesis(hypothesis)
        return HypothesisReference(
            hypothesis_id=reference.record_id, revision=reference.revision,
            content_hash=reference.content_hash,
        )

    def resolve(self, reference: HypothesisReference) -> Hypothesis:
        row = self._connection.execute(
            "SELECT payload_json, content_hash FROM hypotheses WHERE id = ? AND revision = ?",
            (str(reference.hypothesis_id), reference.revision)).fetchone()
        if row is None or row["content_hash"] != reference.content_hash:
            raise KeyError("hypothesis reference cannot be resolved")
        return Hypothesis.model_validate_json(row["payload_json"])

    def record_trial(self, execution: TrialExecution) -> None:
        raise RuntimeError("trial evidence must be persisted through finalize_attempt")

    def record_observation(self, observation: Observation) -> None:
        with self._connection:
            self._connection.execute("INSERT INTO observations VALUES (?, ?, ?, ?, ?)",
                (str(observation.id), str(observation.trial_id), str(observation.observer_id),
                 observation.model_dump_json(), observation.recorded_at.isoformat()))

    def trials_for_experiment(self, experiment: ScientificRecordReference) -> Iterable[TrialExecution]:
        if experiment.record_type is not ScientificRecordType.EXPERIMENT:
            raise ValueError("trial queries require an experiment revision reference")
        rows = self._connection.execute(
            "SELECT payload_json FROM trial_executions WHERE experiment_id = ? AND experiment_revision = ? ORDER BY started_at",
            (str(experiment.record_id), experiment.revision),
        )
        return [TrialExecution.model_validate_json(row["payload_json"]) for row in rows]

    def _validate_hypothesis_lineage(self, hypothesis: Hypothesis) -> None:
        predecessor = hypothesis.predecessor
        if hypothesis.revision == 1:
            if predecessor is not None:
                raise ValueError("the first hypothesis revision cannot have a predecessor")
            return
        if predecessor is None or predecessor.hypothesis_id != hypothesis.id or predecessor.revision != hypothesis.revision - 1:
            raise ValueError("a hypothesis revision must pin its immediately preceding revision")
        self.resolve(predecessor)

    def _write_audit(self, event: AuditEvent) -> None:
        subject = event.subject
        self._connection.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(event.id), event.action.value, subject.record_type.value if subject else None,
             str(subject.record_id) if subject else None, subject.revision if subject else None,
             str(event.actor_id), event.occurred_at.isoformat(), event.model_dump_json()),
        )

    def _write_relation(self, relation: ScientificRelation) -> None:
        self._connection.execute(
            "INSERT INTO scientific_relations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(relation.id), relation.source.record_type.value, str(relation.source.record_id),
             relation.source.revision, relation.relation_type.value, relation.target.record_type.value,
             str(relation.target.record_id), relation.target.revision, relation.model_dump_json()),
        )

    def _register_scientific_record(
        self, table: str, record: object, initial_relations: tuple[ScientificRelation, ...] = (),
    ) -> ScientificRecordReference:
        reference = record.reference()
        predecessor = record.predecessor
        if record.revision == 1:
            if predecessor is not None:
                raise ValueError("the first record revision cannot have a predecessor")
        else:
            if (predecessor is None or predecessor.record_type != reference.record_type
                    or predecessor.record_id != reference.record_id
                    or predecessor.revision != reference.revision - 1):
                raise ValueError("a revision must pin its immediately preceding record revision")
            self.resolve_scientific_record(predecessor)
        for relation in initial_relations:
            if relation.source != reference:
                raise ValueError("initial relations must originate from the record being registered")
            self.resolve_scientific_record(relation.target)
        with self._connection:
            self._connection.execute(
                f"INSERT INTO {table} VALUES (?, ?, ?, ?)",
                (str(reference.record_id), reference.revision, reference.content_hash,
                 record.model_dump_json()),
            )
            if predecessor is not None:
                relation = ScientificRelation(
                    source=reference, relation_type="revises", target=predecessor,
                    rationale="Immutable revision lineage.", asserted_by=record.created_by,
                )
                self._write_relation(relation)
                self._write_audit(AuditEvent(
                    action=AuditAction.RELATION_RECORDED, subject=reference,
                    actor_id=record.created_by, details={"relation_id": str(relation.id)},
                ))
            for relation in initial_relations:
                self._write_relation(relation)
                self._write_audit(AuditEvent(
                    action=AuditAction.RELATION_RECORDED, subject=relation.source,
                    actor_id=relation.asserted_by, details={"relation_id": str(relation.id)},
                ))
            self._write_audit(AuditEvent(
                action=AuditAction.REGISTERED, subject=reference, actor_id=record.created_by,
            ))
        return reference

    def register_question(self, question: ResearchQuestion) -> ScientificRecordReference:
        return self._register_scientific_record("research_questions", question)

    def register_journal_entry(self, entry: JournalEntry) -> ScientificRecordReference:
        return self._register_scientific_record("journal_entries", entry)

    def register_claim(self, claim: Claim) -> ScientificRecordReference:
        return self._register_scientific_record("claims", claim)

    def register_external_reference(self, reference: ExternalReference) -> ScientificRecordReference:
        return self._register_scientific_record("external_references", reference)

    def register_experiment_revision(self, experiment: ExperimentRevision) -> ScientificRecordReference:
        hypothesis = HypothesisReference(
            hypothesis_id=experiment.plan.hypothesis.hypothesis_id,
            revision=experiment.plan.hypothesis.revision,
            content_hash=experiment.plan.hypothesis.content_hash,
        )
        self.resolve(hypothesis)
        reference = experiment.reference()
        hypothesis_reference = ScientificRecordReference(
            record_type="hypothesis", record_id=hypothesis.hypothesis_id,
            revision=hypothesis.revision, content_hash=hypothesis.content_hash,
        )
        relation = ScientificRelation(
            source=reference, relation_type="tests", target=hypothesis_reference,
            rationale="The registered experiment revision tests this hypothesis revision.",
            asserted_by=experiment.created_by,
        )
        return self._register_scientific_record("experiment_revisions", experiment, (relation,))

    def register_hypothesis(
        self, hypothesis: Hypothesis, motivated_by: tuple[ScientificRecordReference, ...] = (),
    ) -> ScientificRecordReference:
        self._validate_hypothesis_lineage(hypothesis)
        pinned = HypothesisReference(hypothesis_id=hypothesis.id, revision=hypothesis.revision,
                                     content_hash=hypothesis.content_hash())
        reference = ScientificRecordReference(record_type="hypothesis", record_id=pinned.hypothesis_id,
                                               revision=pinned.revision, content_hash=pinned.content_hash)
        for source in motivated_by:
            self.resolve_scientific_record(source)
        with self._connection:
            self._connection.execute("INSERT INTO hypotheses VALUES (?, ?, ?, ?)",
                (str(hypothesis.id), hypothesis.revision, pinned.content_hash, hypothesis.model_dump_json()))
            if hypothesis.predecessor is not None:
                prior = ScientificRecordReference(
                    record_type="hypothesis", record_id=hypothesis.predecessor.hypothesis_id,
                    revision=hypothesis.predecessor.revision, content_hash=hypothesis.predecessor.content_hash,
                )
                relation = ScientificRelation(
                    source=reference, relation_type="revises", target=prior,
                    rationale="Immutable revision lineage.", asserted_by=hypothesis.registered_by,
                )
                self._write_relation(relation)
                self._write_audit(AuditEvent(
                    action=AuditAction.RELATION_RECORDED, subject=reference,
                    actor_id=hypothesis.registered_by, details={"relation_id": str(relation.id)},
                ))
            for source in motivated_by:
                relation = ScientificRelation(
                    source=source, relation_type="motivates", target=reference,
                    rationale="Recorded as a design motivation at registration.",
                    asserted_by=hypothesis.registered_by,
                )
                self._write_relation(relation)
                self._write_audit(AuditEvent(
                    action=AuditAction.RELATION_RECORDED, subject=source,
                    actor_id=hypothesis.registered_by, details={"relation_id": str(relation.id)},
                ))
            self._write_audit(AuditEvent(
                action=AuditAction.REGISTERED, subject=reference, actor_id=hypothesis.registered_by,
            ))
        return reference

    def resolve_scientific_record(self, reference: ScientificRecordReference) -> object:
        if reference.record_type is ScientificRecordType.HYPOTHESIS:
            hypothesis = self.resolve(HypothesisReference(
                hypothesis_id=reference.record_id, revision=reference.revision,
                content_hash=reference.content_hash,
            ))
            return hypothesis
        table_and_model = {
            ScientificRecordType.RESEARCH_QUESTION: ("research_questions", ResearchQuestion),
            ScientificRecordType.JOURNAL_ENTRY: ("journal_entries", JournalEntry),
            ScientificRecordType.CLAIM: ("claims", Claim),
            ScientificRecordType.EXTERNAL_REFERENCE: ("external_references", ExternalReference),
            ScientificRecordType.EXPERIMENT: ("experiment_revisions", ExperimentRevision),
        }
        pair = table_and_model.get(reference.record_type)
        if pair is None:
            raise KeyError(f"record type is not persisted by this repository: {reference.record_type}")
        table, model = pair
        row = self._connection.execute(
            f"SELECT payload_json, content_hash FROM {table} WHERE id = ? AND revision = ?",
            (str(reference.record_id), reference.revision),
        ).fetchone()
        if row is None or row["content_hash"] != reference.content_hash:
            raise KeyError("scientific record reference cannot be resolved")
        return model.model_validate_json(row["payload_json"])

    def record_relation(self, relation: ScientificRelation) -> None:
        self.resolve_scientific_record(relation.source)
        self.resolve_scientific_record(relation.target)
        with self._connection:
            self._write_relation(relation)
            self._write_audit(AuditEvent(
                action=AuditAction.RELATION_RECORDED, subject=relation.source,
                actor_id=relation.asserted_by, details={"relation_id": str(relation.id)},
            ))

    def record_belief_assessment(self, assessment: BeliefAssessment) -> None:
        self.resolve_scientific_record(assessment.hypothesis)
        for reference in assessment.basis:
            self.resolve_scientific_record(reference)
        with self._connection:
            self._connection.execute(
                "INSERT INTO belief_assessments VALUES (?, ?, ?, ?, ?, ?)",
                (str(assessment.id), str(assessment.hypothesis.record_id), assessment.hypothesis.revision,
                 str(assessment.observer_id), assessment.assessed_at.isoformat(), assessment.model_dump_json()),
            )
            self._write_audit(AuditEvent(
                action=AuditAction.BELIEF_ASSESSED, subject=assessment.hypothesis,
                actor_id=assessment.observer_id, details={"assessment_id": str(assessment.id)},
            ))

    def append_audit_event(self, event: AuditEvent) -> None:
        with self._connection:
            self._write_audit(event)
    def register_entropy_policy(self,spec:EntropyPolicySpecification)->EntropyPolicyReference:
        ref=EntropyPolicyReference(policy_id=spec.id,revision=spec.revision,content_hash=spec.content_hash())
        with self._connection:
            self._connection.execute("INSERT INTO entropy_policy_specifications VALUES (?,?,?,?)",(str(spec.id),spec.revision,ref.content_hash,spec.model_dump_json()))
            self._connection.execute("INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?)",(str(uuid4()),"registered","entropy_policy",str(spec.id),spec.revision,str(spec.created_by),spec.created_at.isoformat(),spec.model_dump_json()))
        return ref
    def resolve_entropy_policy(self,ref:EntropyPolicyReference)->EntropyPolicySpecification:
        row=self._connection.execute("SELECT payload_json,content_hash FROM entropy_policy_specifications WHERE id=? AND revision=?",(str(ref.policy_id),ref.revision)).fetchone()
        if not row or row["content_hash"]!=ref.content_hash: raise KeyError("pinned entropy policy cannot be resolved")
        return EntropyPolicySpecification.model_validate_json(row["payload_json"])
    def register_analysis_specification(self,spec:AnalysisSpecification)->None:
        with self._connection: self._connection.execute("INSERT OR IGNORE INTO analysis_specifications VALUES (?,?,?,?)",(str(spec.id),spec.revision,spec.content_hash(),spec.model_dump_json()))
    def create_analysis_run(self,run:AnalysisRun)->None:
        with self._connection: self._connection.execute("INSERT INTO analysis_runs VALUES (?,?,?)",(str(run.id),run.status,run.model_dump_json()))
    def executions_for_cohort(self,cohort:CohortSnapshot):
        result=[]
        for member in sorted(cohort.members,key=lambda x:x.inclusion_order):
            row=self._connection.execute("SELECT payload_json FROM trial_executions WHERE id=?",(str(member.execution_id),)).fetchone()
            if row: result.append(TrialExecution.model_validate_json(row["payload_json"]))
        return result
    def finalize_analysis_run(self,run:AnalysisRun,result:AnalysisResult)->None:
        with self._connection:
            self._connection.execute("UPDATE analysis_runs SET status=? WHERE id=?",(result.status,str(run.id)))
            self._connection.execute("INSERT INTO analysis_results VALUES (?,?,?,?)",(str(result.id),str(run.id),result.status,result.model_dump_json()))

    def _control_event(self, event: ControlEvent) -> None:
        self._connection.execute("INSERT INTO control_events VALUES (?, ?, ?, ?, ?, ?)", (str(event.id),str(event.experiment_run_id),str(event.trial_attempt_id) if event.trial_attempt_id else None,event.event_type.value,event.model_dump_json(),event.occurred_at.isoformat()))
    def create_run(self, run: ExperimentRun, event: ControlEvent) -> ExperimentRun:
        self.resolve_scientific_record(run.experiment_revision)
        with self._connection:
            try:
                self._connection.execute("INSERT INTO experiment_runs VALUES (?, ?, ?, ?)",(str(run.id),run.idempotency_key,run.state.value,run.model_dump_json()))
            except sqlite3.IntegrityError:
                existing=self.find_run_by_key(run.idempotency_key)
                if existing and existing.command_hash == run.command_hash:
                    return existing
                raise ValueError("idempotency key is already bound to a different command")
            self._control_event(event)
        return run
    def find_run_by_key(self,key:str)->ExperimentRun|None:
        row=self._connection.execute("SELECT payload_json FROM experiment_runs WHERE idempotency_key=?",(key,)).fetchone(); return ExperimentRun.model_validate_json(row["payload_json"]) if row else None
    def get_run(self,run_id:UUID)->ExperimentRun:
        row=self._connection.execute("SELECT payload_json FROM experiment_runs WHERE id=?",(str(run_id),)).fetchone()
        if not row: raise KeyError("experiment run not found")
        return ExperimentRun.model_validate_json(row["payload_json"])
    def transition_run(self,run_id:UUID,state:ExperimentRunState,event:ControlEvent)->ExperimentRun:
        row=self._connection.execute("SELECT payload_json FROM experiment_runs WHERE id=?",(str(run_id),)).fetchone()
        if not row: raise KeyError("experiment run not found")
        old=ExperimentRun.model_validate_json(row["payload_json"]); require_transition(old.state,state,RUN_TRANSITIONS)
        new=old.model_copy(update={"state":state,"updated_at":event.occurred_at})
        with self._connection:
            self._connection.execute("UPDATE experiment_runs SET state=?,payload_json=? WHERE id=?",(state.value,new.model_dump_json(),str(run_id))); self._control_event(event)
        return new
    def create_attempt(self,attempt:TrialAttempt,event:ControlEvent)->TrialAttempt:
        run=self.get_run(attempt.experiment_run_id)
        if run.state not in {ExperimentRunState.SCHEDULED,ExperimentRunState.RUNNING,ExperimentRunState.PAUSED}: raise ValueError("cannot create attempts for terminal run")
        with self._connection:
            self._connection.execute("INSERT INTO trial_attempts VALUES (?, ?, ?, ?, ?, ?)",(str(attempt.id),str(attempt.experiment_run_id),str(attempt.trial_spec_id),attempt.idempotency_key,attempt.state.value,attempt.model_dump_json())); self._control_event(event)
        return attempt
    def transition_attempt(self,attempt_id:UUID,state:TrialAttemptState,event:ControlEvent,error_category=None,error_message:str|None=None)->TrialAttempt:
        row=self._connection.execute("SELECT payload_json FROM trial_attempts WHERE id=?",(str(attempt_id),)).fetchone()
        if not row: raise KeyError("trial attempt not found")
        old=TrialAttempt.model_validate_json(row["payload_json"]); require_transition(old.state,state,ATTEMPT_TRANSITIONS)
        new=old.model_copy(update={"state":state,"updated_at":event.occurred_at,"error_category":error_category,"error_message":error_message})
        with self._connection:
            self._connection.execute("UPDATE trial_attempts SET state=?,payload_json=? WHERE id=?",(state.value,new.model_dump_json(),str(attempt_id))); self._control_event(event)
        return new
    def attempts_for_run(self,run_id:UUID)->Iterable[TrialAttempt]:
        return [TrialAttempt.model_validate_json(r["payload_json"]) for r in self._connection.execute("SELECT payload_json FROM trial_attempts WHERE experiment_run_id=? ORDER BY rowid",(str(run_id),))]
    def append_control_event(self,event:ControlEvent)->None:
        with self._connection: self._control_event(event)
    def finalize_attempt(self,execution:TrialExecution,state:TrialAttemptState,event:ControlEvent,error_category=None,error_message:str|None=None)->TrialAttempt:
        if execution.status.value not in {"completed", "failed", "cancelled"}: raise ValueError("only terminal executions may be persisted")
        run=self.get_run(execution.experiment_run_id)
        if execution.provenance.experiment_revision != run.experiment_revision: raise ValueError("execution experiment reference does not match run")
        row=self._connection.execute("SELECT payload_json FROM trial_attempts WHERE id=?",(str(execution.trial_attempt_id),)).fetchone()
        if not row: raise KeyError("trial attempt not found")
        attempt=TrialAttempt.model_validate_json(row["payload_json"])
        if attempt.experiment_run_id != run.id or attempt.trial_spec_id != execution.trial_spec_id or attempt.attempt_number != execution.attempt_number or attempt.idempotency_key != execution.idempotency_key: raise ValueError("execution does not match trial attempt")
        require_transition(attempt.state,state,ATTEMPT_TRANSITIONS)
        new=attempt.model_copy(update={"state":state,"updated_at":event.occurred_at,"error_category":error_category,"error_message":error_message})
        with self._connection:
            self._connection.execute("INSERT INTO trial_executions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",(str(execution.id),str(run.experiment_revision.record_id),run.experiment_revision.revision,str(execution.trial_spec_id),execution.status.value,execution.model_dump_json(),execution.started_at.isoformat(),execution.finished_at.isoformat() if execution.finished_at else None))
            self._connection.execute("UPDATE trial_attempts SET state=?,payload_json=? WHERE id=?",(state.value,new.model_dump_json(),str(attempt.id)))
            self._control_event(event)
        return new
